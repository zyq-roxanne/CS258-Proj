from matplotlib import pyplot as plt
import os, sys
from bisect import bisect_left

import constants
import util


cache_qr_mat = {}

class QRcode:
    def __init__(self, version = None,
                err_corr = constants.ERR_CORR_M,
                box_size = 10, border = 4,
                mask_pattern = None):
        if box_size < 0 or border < 0:
            raise ValueError('Expect box size and border > 0.')
        self.version = version and int(version)
        self.err_corr = int(err_corr)
        self.box_size = int(box_size)
        self.border = int(border)
        self.mask_pattern = mask_pattern
        self.clear()

    def clear(self):
        '''
        Reset all data
        '''
        self.modules = None
        self.modules_cnt = 0 # No of modules/side
        self.data_cache = None
        self.data_list = []

    def add_data(self, data):
        '''
        Add data to QRcode
        '''
        if isinstance(data, util.QRData):
            self.data_list.append(data)
        else:
            self.data_list.append(util.QRData(data))
        self.data_cache = None

    def make(self, fit = True):
        '''
        A wrapper
        Data Ananlysis + Data Encodation + Error Correction Coing + Strutrue final Message + Placement in Matrix
        :param fit: True -> use best_fit to find an optimal size(version)
        '''
        if fit or(self.version == None):
            self.best_fit(start=self.version)
        if self.mask_pattern is None:
            self.makeImpl(False, self.best_mask_pattern())
        else:
            self.makeImpl(False, self.mask_pattern)

    def best_fit(self,start = None):
        '''
        Finds an optimal size(version) for data
        '''
        if start == None:
            start = 1
        if start < 1 or start > 40:
            raise ValueError("Invalid version")
        
        bits_number = util.bits_number_for_version(start)
        buffer = util.BitBuffer()
        for data in self.data_list:
            buffer.put(data.mode, 4)
            buffer.put(len(data), bits_number[data.mode])
            data.write(buffer)
        
        bits_needed = len(buffer)
        self.version = bisect_left(
            util.BIT_LIMIT_TABLE[self.err_corr], bits_needed, start
        )

        if self.version > 40:
            raise OverflowError("Data Overflow!")

        # Check if our guess is too low
        if bits_number is not util.bits_number_for_version(self.version):
            self.best_fit(start = self.version)
        return self.version
    
    def best_mask_pattern(self):
        '''
        Find the optimal mask pattern
        '''
        mask_pattern = 0
        min_lost_needed = 0
        
        for i in range(8):
            self.makeImpl(True, i)

            lost_current = util.lost_calculator(self.modules)

            if i==0 or min_lost_needed > lost_current:
                min_lost_needed = lost_current
                mask_pattern = i

        return mask_pattern

    def makeImpl(self, test, mask_pattern):
        '''
        Make mat
        '''
        if self.version < 1 or self.version > 40:
            raise ValueError('Invalid version')
        self.modules_cnt = self.version*4 + 17

        if self.version in cache_qr_mat:
            self.modules = util.copy_mat(cache_qr_mat[self.version])
        else:
            # Initialize the mat
            self.modules = [None] * self.modules_cnt

            for row in range(self.modules_cnt):
                self.modules[row] = [None]* self.modules_cnt
                
            # set up alignment patterns
            self.setup_finder_pattern(0, 0)
            self.setup_finder_pattern(self.modules_cnt - 7, 0)
            self.setup_finder_pattern(0, self.modules_cnt - 7)
            self.setup_position_align_pattern()
            self.setup_timing_pattern()

            # save current modules
            cache_qr_mat[self.version] = util.copy_mat(self.modules)

        self.setup_type_info(test, mask_pattern)

        if self.version >= 7:
            self.setup_version_info(test)

        if self.data_cache == None:
            self.data_cache = util.put_data(self.version, self.err_corr, self.data_list)

        self.mapping(self.data_cache, mask_pattern)

    def setup_finder_pattern(self, row, col):
        '''
        Set the finder pattern for localization
        Usually we need 3 finder pattern 1:1:3:1:1
        '''
        for r in range(-1, 8):
            if row + r <= -1 or self.modules_cnt <= row + r:
                continue

            for c in range(-1, 8):

                if col + c <= -1 or self.modules_cnt <= col + c:
                    continue
                if (
                    (0 <= r <= 6 and c in {0, 6})
                    or (0 <= c <= 6 and r in {0, 6})
                    or (2 <= r <= 4 and 2 <= c <= 4)
                ):
                    self.modules[row + r][col + c] = True
                else:
                    self.modules[row + r][col + c] = False

    def setup_position_align_pattern(self):
        '''
        Align Pattern for high version
        '''
        pos = constants.PATTERN_POSITION[self.version]
        for i in range(len(pos)):
            row = pos[i]

            for j in range(len(pos)):
                col = pos[j]

                if self.modules[row][col] is not None:
                    continue

                for r in range(-2, 3):

                    for c in range(-2, 3):

                        if (r == -2 or r == 2 or c == -2 or c == 2 or
                                (r == 0 and c == 0)):
                            self.modules[row + r][col + c] = True
                        else:
                            self.modules[row + r][col + c] = False

    def setup_timing_pattern(self):
        '''
        Set up Timing pattern
        Used as axis in QR code
        '''
        for r in range(8, self.modules_cnt - 8):
            if self.modules[r][6] is not None:
                continue
            self.modules[r][6] = (r % 2 == 0)

        for c in range(8, self.modules_cnt - 8):
            if self.modules[6][c] is not None:
                continue
            self.modules[6][c] = (c % 2 == 0)

    def setup_type_info(self, test, mask_pattern):
        '''
        calculate data and error correction info 
        setup type information
        '''
        data = (self.err_corr << 3) | mask_pattern 
        data_BCH = util.BCH_code_generator(data)

        # vertical
        for r in range(15):
            mod = (not test and ((data_BCH >> r) & 1) == 1)
            if r < 6:
                self.modules[r][8] = mod
            elif r < 8:
                self.modules[r + 1][8] = mod
            else:
                self.modules[self.modules_cnt - 15 + r][8] = mod

        # horizontal
        for c in range(15):
            mod = (not test and ((data_BCH >> c) & 1) == 1)
            if c < 8:
                self.modules[8][self.modules_cnt - c - 1] = mod
            elif c < 9:
                self.modules[8][15 - c] = mod
            else:
                self.modules[8][15 - c - 1] = mod

        # fixed module
        self.modules[self.modules_cnt - 8][8] = not test

    def setup_version_info(self, test):
        '''
        Setup the qr code about version info for high version
        '''
        data_BCH = util.BCH_code_version_info(self.version)

        for r in range(18):
            mod = (not test and ((data_BCH >> r) & 1) == 1)
            self.modules[r // 3][r%3 + self.modules_cnt - 11] = mod

        for c in range(18):
            mod = (not test and ((data_BCH >> c) & 1) == 1)
            self.modules[c%3 + self.modules_cnt - 11][c // 3] = mod

        return

    def mapping(self, data, mask_pattern):
        '''
        Module placement in matrix
        Interleave the data and error correction codewords from each block 
        and add remainder bits as necessar
        See in 8.3
        '''
        increment = -1
        r = self.modules_cnt - 1
        bitIndex = 7
        byteIdex = 0

        mask_func = util.mask_function(mask_pattern)
        length = len(data)

        for c in range(self.modules_cnt - 1, 0, -2):
            if c <= 6:
                c -= 1
            col_range = (c, c-1)

            while True:
                for c_ in col_range:
                    if self.modules[r][c_] == None:
                        dark = False

                        if byteIdex < length:
                            dark = (((data[byteIdex] >> bitIndex) & 1) == 1)

                        if mask_func(r, c_):
                            dark = not dark
                        
                        self.modules[r][c_] = dark

                        bitIndex -= 1

                        if bitIndex == -1:
                            byteIdex += 1
                            bitIndex = 7

                r += increment

                if r < 0 or self.modules_cnt <= r:
                    r -= increment
                    increment = -increment
                    break

    def get_mat(self):
        '''
        Return the Qrcode in mat
        save if name and save path given
        '''

        if self.data_cache == None:
            self.make()
        
        if not self.border:
            return self.modules

        mat_size_with_border = self.modules_cnt + 2 * self.border
        mat = [[False] * mat_size_with_border] * self.border 
        margain = [False] * self.border
        for module in self.modules:
            mat.append(margain + module + margain)
        mat.extend([[False] * mat_size_with_border] * self.border)

        return mat

        
    def make_image(self, name = None, save_dir = None):
        '''
        Make QRcode image
        param: name without suffix
        '''

        mat = self.get_mat()

        if save_dir == None:
            save_dir = 'MyQrCode'
        
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)

        if name == None:
            name = ''.join(repr(data) for data in self.data_list).replace('\'', '')[1:]
            if len(name) > 15:
                name = name[:15]
        
        import numpy as np
        array = np.array(mat, int)

        
        # delete margain
        plt.margins(0,0)
        fig = plt.figure(frameon=False)
        fig.set_size_inches(5,5)
        ax = plt.Axes(fig, [0., 0., 1., 1.])
        ax.set_axis_off()
        fig.add_axes(ax)

        # save fig
        plt.imshow(array, 'gray_r')
        fig.savefig(save_dir + '/' + name + '.png')
        plt.close()

        # plt.imsave(fname = save_dir + '/' + name + '.png', arr = mat, cmap = 'gray_r', dpi = 500)
        
    

if __name__ == '__main__':
    # q = QRcode()
    # q.add_data('The significant inscription found on an old key - “If I rest, I rust” - would be an excellent motto for those who are afflicted with the slightest bit of idleness. Even the most industrious person might adopt it with advantage to serve as a reminder that, if one allows his faculties to rest, like the iron in the unused key, they will soon show signs of rust and, ultimately, cannot do the work required of them.')
    # q.make_image(name = 'A long sentence')

    q2 = QRcode(mask_pattern=3)
    q2.add_data('信息论')
    q2.make_image(name = '信息论 Mask011')
    # q2.clear()
    # q2.add_data('information theory')
    # q2.make_image(name = 'information theory')

    # from pyzbar import pyzbar
    # from PIL import Image

    # result = pyzbar.decode(Image.open('MyQrCode/xinxilun.png'), symbols=[pyzbar.ZBarSymbol.QRCODE])
    # print(result)
    # print(result[0][0])
