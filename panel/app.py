from flask import Flask,jsonify

app=Flask(__name__)

@app.route('/')
def home():
    return 'Custom Panel v16'

@app.route('/api/status')
def status():
    return jsonify({'status':'ok','version':'16-final'})

app.run(host='0.0.0.0',port=5000)
