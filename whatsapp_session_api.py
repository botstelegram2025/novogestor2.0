from flask import Blueprint, jsonify, request

session_api = Blueprint('session_api', __name__, url_prefix='/api/session')

_session_state = {}

def init_session_manager(db):
    # compat: nada a fazer, mas mantemos referência se necessário
    _session_state['db'] = db

@session_api.route('/status', methods=['GET'])
def status():
    session_id = request.args.get('session_id', 'default')
    return jsonify({'session_id': session_id, 'qr_needed': False, 'connected': True})

@session_api.route('/qr', methods=['GET'])
def qr():
    return jsonify({'success': True, 'qr_code': ''})

@session_api.route('/send-test', methods=['POST'])
def send_test():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({'success': True, 'echo': data})
