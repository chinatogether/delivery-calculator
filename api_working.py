from flask import Flask, render_template, request, jsonify, redirect
from urllib.parse import unquote, quote
import json
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/result')
def result():
    results_param = request.args.get('results', None)
    try:
        if results_param:
            results = json.loads(unquote(results_param))
            return render_template('result.html', results=results)
        else:
            return render_template('result.html', error="Нет данных")
    except Exception as e:
        return render_template('result.html', error=str(e))

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "port": 8061})

@app.route('/calculate')
def calculate():
    return jsonify({"error": "Функция расчета временно недоступна"}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8061, debug=True)
EOF
