
import constants


class RSBlock:

    def __init__(self, total_count, data_count):
        self.total_count = total_count
        self.data_count = data_count

RS_BLOCK_OFFSET = {
    constants.ERR_CORR_L: 0,
    constants.ERR_CORR_M: 1,
    constants.ERR_CORR_Q: 2,
    constants.ERR_CORR_H: 3,
}

def rs_blocks(version, err_corr):
    if err_corr not in RS_BLOCK_OFFSET:  # pragma: no cover
        raise Exception(
            "bad rs block @ version: {} / error_correction: {}".format(version, err_corr))
    offset = RS_BLOCK_OFFSET[err_corr]
    rs_block = constants.RS_BLOCK_TABLE[(version - 1) * 4 + offset]

    blocks = []

    for i in range(0, len(rs_block), 3):
        count, total_count, data_count = rs_block[i:i + 3]
        for j in range(count):
            blocks.append(RSBlock(total_count, data_count))

    return blocks

# Precompute bit count limits, indexed by error correction level and code size
_data_count = lambda block: block.data_count
BIT_LIMIT_TABLE = [
    [0] + [8*sum(map(_data_count, rs_blocks(version, err_corr)))  for version in range(1, 41)]
    for err_corr in range(4)
]

# Polynomials class

exponents = [i for i in range(256)]
log = [i for i in range(256)]

for i in range(8):
    exponents[i] = 1 << i

for i in range(8, 256):
    exponents[i] = (exponents[i - 4] ^ exponents[i - 5] ^ exponents[i - 6] ^ exponents[i - 8])

for i in range(256-1):
    log[exponents[i]] = i

def _log(n):
    
    if n < 1:  # pragma: no cover
        raise ValueError(f"_log({n})")
    return log[n]

def _exp(n):
    return exponents[n % 255]

class Polynomial:

    def __init__(self, num, shift):
        if not num:  # pragma: no cover
            raise Exception(f"{len(num)}/{shift}")

        for offset in range(len(num)):
            if num[offset] != 0:
                break
        else:
            offset += 1

        self.num = num[offset:] + [0] * shift

    def __getitem__(self, index):
        return self.num[index]

    def __iter__(self):
        return iter(self.num)

    def __len__(self):
        return len(self.num)

    def __mul__(self, other):
        num = [0] * (len(self) + len(other) - 1)

        for i, item in enumerate(self):
            for j, other_item in enumerate(other):
                num[i + j] ^= _exp(_log(item) + _log(other_item))

        return Polynomial(num, 0)

    def __mod__(self, other):
        difference = len(self) - len(other)
        if difference < 0:
            return self

        ratio = _log(self[0]) - _log(other[0])

        num = [
            item ^ _exp(_log(other_item) + ratio)
            for item, other_item in zip(self, other)]
        if difference:
            num.extend(self[-difference:])

        # recursive call
        return Polynomial(num, 0) % other

# QRcode valid data type
class QRData:
    '''
    Data valid for Qr 
    '''
    def __init__(self, data, mode = None):
        if not isinstance(data, bytes):
            data = data.encode('utf-8')
        self.data = data

        if mode == None:
            self.mode = self.best_mode()
        else:
            self.mode = mode
            if mode not in constants.MODE_INDICATORS:
                raise TypeError("Invalid mode!")
            if mode < self.best_mode():
                raise ValueError("Data cannot be represented in mode {}".format(mode))

    
    def __len__(self):
        return len(self.data)

    def write(self, buffer):
        if self.mode == constants.NUMERIC_MODE:
            for i in range(0,len(self.data), 3):
                chars = self.data[i:i+3]
                bit_length = constants.NUMBER_LENGTH[len(chars)]
                buffer.put(int(chars), bit_length)
        elif self.mode == constants.ALPHANUMERIC_MODE:
            for i in range(0, len(self.data), 2):
                chars = self.data[i:i+2]
                if len(chars) > 1:
                    buffer.put(constants.ALPHANUMERIC_NUM.find(chars[0]) * 45
                    + constants.ALPHANUMERIC_NUM.find(chars[1]), 11)
                else:
                    buffer.put(constants.ALPHANUMERIC_NUM.find(chars[0]),6)
        else:
            data = self.data
            for c in data:
                buffer.put(c, 8) # utf-8 without simple compression
        

    def __repr__(self):
        return repr(self.data)

    def best_mode(self):
        '''
        Calculate the best mode for data
        '''
        data = self.data
        if data.isdigit():
            return constants.NUMERIC_MODE
        elif constants.RE_ALPHANUMERIC_NUM.match(data):
            return constants.ALPHANUMERIC_MODE
        else:
            return constants.EIGHT_BIT_BYTE_MODE



class BitBuffer:
    '''
    Library to store data by bit
    '''
    def __init__(self):
        self.buffer = []
        self.length = 0

    def __repr__(self):
        return '.'.join([str(n) for n in self.buffer])

    def __len__(self):
        return self.length

    def get(self, index):
        '''
        Gets the n-th elements of the bitarray
        '''
        buf_index = int(index/8)
        position = index % 8
        return (self.buffer[buf_index] & (1<< (7- position))) == 1

    def set(self, bit = 1):
        '''
        Sets the back elements of the bitarray
        '''
        length = self.length
        buf_index = int(length/8)
        position = length % 8
        if len(self.buffer) <= buf_index:
            self.buffer.append(0)
        if bit:
            self.buffer[buf_index] =self.buffer[buf_index] | 1 << (7 - position)
        self.length += 1

    def put(self, data, length):
        '''
        put num by bit
        '''
        for i in range(length):
            self.set(((data >> (length-i-1)) & 1) == 1)


def bits_number_for_version(version):
    if version < 10:
        return constants.MODE_SIZE_SMALL
    elif version < 27:
        return constants.MODE_SIZE_MEDIUM
    else:
        return constants.MODE_SIZE_LARGE

def copy_mat(x):
    return [row[:] for row in x]

def BCH_digit(data):
    '''
    Count Bits in binary representation of data for error correction
    '''
    digit = 0
    while data != 0:
        digit += 1
        data >>= 1
    return digit

def BCH_code_generator(data):
    '''
    Error correction bit calculation According to Annex C
    '''
    d = data << 10 # raise power to the 10-th
    while BCH_digit(d) - BCH_digit(constants.G15) >= 0: # divide by G(x)
        d ^= (constants.G15 << (BCH_digit(d) - BCH_digit(constants.G15))) 
        # Add coefficient string of above remainder polynomial to Format Information data string
    return ((data << 10) | d) ^ constants.G15_MASK # XOR with mask

def BCH_code_version_info(data):
    '''
    Error correction Version Information According to Annex D
    '''
    d = data << 12 # raise power to (18-6)-th
    while BCH_digit(d) - BCH_digit(constants.G18) >= 0: 
        d ^= (constants.G18 << (BCH_digit(d) - BCH_digit(constants.G18)))
        # Dicide by G18 and add
    return (data << 12) | d

def put_data(version, err_corr, datalist):
    '''
    Data encodation process
    '''
    buffer = BitBuffer()
    for data in datalist:
        buffer.put(data.mode, 4)
        try:
            buffer.put(len(data), bits_number_for_version(version)[data.mode])
        except:
            raise TypeError('Invalid mode')
        
        data.write(buffer)

    # Calculate the maximum bits
    blocks = rs_blocks(version, err_corr=err_corr)
    max_bit = sum(b.data_count * 8 for b in blocks)
    if len(buffer) > max_bit:
        raise OverflowError('Data overflow for current version.')
    
    # Terminate
    for _ in range(min(max_bit - len(buffer), 4)):
        buffer.set(False)

    # Rearrangement
    if len(buffer) % 8: # rearrange if there is remaining bit
        for _ in range(8-len(buffer) % 8):
            buffer.set(False)

    # Divide into 8-bit codewords, adding padding bits
    padding_bytes = (max_bit - len(buffer)) // 8
    
    for i in range(padding_bytes):
        if i % 2:
            buffer.put(constants.PAD1, 8)
        else:
            buffer.put(constants.PAD0, 8)

    return put_bytes(buffer, blocks)

def put_bytes(buffer, rs_blocks):
    '''
    setup the error correction codeword
    '''
    offset = 0

    max_data_cnt = 0
    max_err_cnt = 0

    data_encode = [0] * len(rs_blocks)
    err_encode = [0] * len(rs_blocks)

    for r in range(len(rs_blocks)):
        
        data_cnt = rs_blocks[r].data_count
        err_cnt = rs_blocks[r].total_count - data_cnt

        max_data_cnt = max(max_data_cnt, data_cnt)
        max_err_cnt = max(max_err_cnt, err_cnt)

        data_encode[r] = [0] * data_cnt

        for i in range(len(data_encode[r])):
            data_encode[r][i] = 255 & buffer.buffer[i + offset]
        offset += data_cnt

        # Get error correction Polynomal
        if err_cnt in constants.rsPoly:
            Poly = Polynomial(constants.rsPoly[err_cnt], 0)
        else:
            Poly = Polynomial([1], 0)
            for i in range(err_cnt):
                Poly = Poly * Polynomial([1, _exp(i)], 0)

        rawPoly = Polynomial(data_encode[r], len(Poly) - 1)

        modPoly = rawPoly % Poly
        err_encode[r] = [0] * (len(Poly) - 1)
        for i in range(len(err_encode[r])):
            modIndex = len(modPoly) - len(err_encode[r]) + i
            err_encode[r][i] = modPoly[modIndex] if (modIndex >= 0) else 0
    total_cnt = sum(block.total_count for block in rs_blocks)
    data = [None] * total_cnt
    index = 0

    for i in range(max_data_cnt):
        for r in range(len(rs_blocks)):
            if i < len(data_encode[r]):
                data[index] = data_encode[r][i]
                index += 1

    for i in range(max_err_cnt):
        for r in range(len(rs_blocks)):
            if i < len(err_encode[r]):
                data[index] = err_encode[r][i]
                index += 1

    return data

def mask_function(mask_pattern):
    '''
    Give the mask funtion for given pattern 000-111
    According to Table 23
    '''
    if mask_pattern == 0:
        return lambda i, j: (i + j) % 2 == 0
    elif mask_pattern == 1:
        return lambda i, j: i % 2 == 0
    elif mask_pattern == 2:
        return lambda i, j: j % 3 == 0
    elif mask_pattern == 3:
        return lambda i, j: (i + j) % 3 == 0
    elif mask_pattern == 4:
        return lambda i, j: (i // 2 + j // 3) % 2 == 0
    elif mask_pattern == 5:
        return lambda i, j: (i*j) % 2 + (i*j) % 3 == 0
    elif mask_pattern == 6:
        return lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0
    elif mask_pattern == 7:
        return lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0
    else:
        raise TypeError('Invalid mask pattern {}'.format(mask_pattern))

def lost_calculator(modules):
    '''
    Scoring penalty points for each orrcurence of defined features
    See in 8.8.2 and Table 24
    '''
    modules_cnt = len(modules)

    return lost_count_1(modules, modules_cnt) + lost_count_2(modules, modules_cnt) + lost_count_3(modules, modules_cnt) + lost_count_4(modules, modules_cnt)

def lost_count_1(modules, modules_cnt):
    '''
    Adjacent modules in row/column in same color
    No. of modules = (5 + i) -> Points = N1 + i
    '''         
    points = 0

    for r in range(modules_cnt):
        previous_color = modules[r][0]
        i = 1
        for c in range(1, modules_cnt):
            if modules[r][c] == previous_color:
                i += 1 # calculate consecutive modules
            else:
                if i >= 5: # end consecutiona plus evaluation condition satisfied!
                    points += i + constants.MASK_EVAL_N1 - 5
                i = 1
                previous_color = modules[r][c]
        if i >= 5:
            points += i + constants.MASK_EVAL_N1 - 5

    for c in range(modules_cnt):
        previous_color = modules[0][c]
        i = 1
        for r in range(1, modules_cnt):
            if modules[r][c] == previous_color:
                i += 1
            else:
                if i >= 5:
                    points += i + constants.MASK_EVAL_N1 - 5
                i = 1
                previous_color = modules[r][c]
        if i >= 5:
            points += i + constants.MASK_EVAL_N1 - 5
    
    return points


def lost_count_2(modules, modules_cnt):
    '''
    Block of modules in same color
    Block size = m * n -> points = n2 * (m-1) * (n-1)
    '''
    points = 0

    modules_range = range(modules_cnt - 1) # the last row/col does not form a block
    
    # divide block into 2*2
    # 1 2 3
    # 4 5 6
    # if 2!= 5 -> no block
    for r in modules_range:
        row = modules[r]
        next_row = modules[r + 1]
        col_iterator = iter(modules_range)
        for c in col_iterator:
            top_right = row[c + 1]
            if top_right != next_row[c + 1]: # no block before
                next(col_iterator, None)
            elif top_right != row[c]:
                continue
            elif top_right != next_row[c]:
                continue
            else:
                points += constants.MASK_EVAL_N2 
    return points

def lost_count_3(modules, modules_cnt):
    '''
    1:1:3:1:1 Ratio Detection
    pattern1: 10111010000
    pattern2: 00001011101
    N3
    '''
    # horspool algorithm
    # row[c + 10] == True, pattern1 shift 4, pattern2 shift 2. min = 2

    points = 0
    
    for r in range(modules_cnt):
        row = modules[r]
        col_iter = iter(range(modules_cnt - 10))
        for c in col_iter:
            if(
                not row[c + 1] and row[c + 4]
                and not row[c + 5] and row[c + 6]
                and not row[c + 9]
                and(
                    row[c] and row[c + 2] and row[c + 3]
                    and not row[c + 7] and not row[c + 8] and not row[c + 10]
                or
                    not row[c] and not row[c + 2] and not row[c + 3]
                    and row[c + 7] and row[c + 8] and row[c + 10]
                )
            ):
                points += constants.MASK_EVAL_N3

            if row[c + 10]: # horspool
                next(col_iter, None)
    
    for c in range(modules_cnt):
        row_iter = iter(range(modules_cnt - 10))
        for r in row_iter:
            if(
                not modules[r + 1][c] and modules[r + 4][c]
                and not modules[r + 5][c] and modules[r + 6][c]
                and not modules[r + 9][c]
                and(
                    modules[r][c] and modules[r + 2][c] and modules[r + 3][c]
                    and not modules[r + 7][c] and not modules[r + 8][c] and not modules[r + 9][c]
                or
                    not modules[r][c] and not modules[r + 2][c] and not modules[r + 3][c]
                    and modules[r + 7][c] and modules[r + 8][c] and modules[r + 10][c]
                )
            ):
                points += constants.MASK_EVAL_N3
            if modules[r + 10][c]:
                next(row_iter, None)
    return points

def lost_count_4(modules, modules_cnt):
    '''
    Proportion of dark in the entire mat
    50 +- (5 * k) % to 50 +- (5* (k+1)) % -> points = N4 * k
    '''
    dark_cnt = sum(map(sum, modules))
    percent = dark_cnt / modules_cnt / modules_cnt * 100
    return constants.MASK_EVAL_N4 * int(abs(percent-50)) // 5

    
    
