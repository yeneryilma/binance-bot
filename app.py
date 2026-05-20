from flask import Flask
from flask_socketio import SocketIO, emit
from config import Config
from routes.web import web_bp
from routes.api import api_bp, set_socketio
from services.portfolio_service import build_state
import requests

socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)
    return app

app = create_app()
set_socketio(socketio)
socketio.init_app(app)

@app.route('/my-ip')
def my_ip():
    return request.remote_addr

@socketio.on('connect')
def on_connect(auth=None):
    emit('state_update', build_state())

if __name__ == '__main__':
    print(f"Bot UI: http://localhost:{Config.PORT}")
    socketio.run(app, host=Config.HOST, port=Config.PORT, debug=False, allow_unsafe_werkzeug=True)
