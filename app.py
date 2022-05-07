from flask import Flask, redirect, render_template, request, url_for
import QRcode
import os

app = Flask(__name__)

def render_index(request, template, result):
    if request.method == 'POST':
        data = request.form['data']
        return redirect(url_for(result, data = data))
    return render_template(template)


def render_result(request, template, result):
    if request.method == 'POST':
        data = request.form['data']
        return redirect(url_for(result, data = data))

    data = request.args.get('data')
    err_corr = request.args.get('err_corr')
    basedir = os.path.abspath(os.path.dirname(__file__))
    print(basedir)

    q = QRcode.QRcode(err_corr = int(err_corr))
    q.add_data(data)
    q.make_image(name='1',save_dir='static')

    return render_template(template, data = data, name = basedir + '/MyQrCode/1.png')

@app.route('/', methods = ['POST','GET'])
def index():
    return render_index(request, 'index.html', 'result')

@app.route('/result', methods = ['POST','GET'])
def result():
    return render_result(request, 'result.html', 'result')

if __name__ == '__main__':
    app.run(debug=True, port=8081)