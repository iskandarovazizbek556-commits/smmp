import hashlib
from flask import Blueprint, request, jsonify

click_bp = Blueprint('click', __name__)

# Click sozlamalari
CLICK_SERVICE_ID = "YOUR_SERVICE_ID"
CLICK_MERCHANT_ID = "YOUR_MERCHANT_ID"
CLICK_SECRET_KEY = "YOUR_SECRET_KEY"


def generate_sign(params):
    sign_string = (
        params['click_trans_id'] +
        params['service_id'] +
        CLICK_SECRET_KEY +
        params['merchant_trans_id'] +
        params['amount'] +
        params['action'] +
        params['sign_time']
    )
    return hashlib.md5(sign_string.encode('utf-8')).hexdigest()


@click_bp.route('/prepare', methods=['POST'])
def prepare():
    data = request.form

    sign = generate_sign(data)

    if sign != data.get("sign_string"):
        return jsonify({
            "error": -1,
            "error_note": "Invalid sign"
        })

    return jsonify({
        "click_trans_id": data['click_trans_id'],
        "merchant_trans_id": data['merchant_trans_id'],
        "merchant_prepare_id": "123456",
        "error": 0,
        "error_note": "Success"
    })


@click_bp.route('/complete', methods=['POST'])
def complete():
    data = request.form

    sign = generate_sign(data)

    if sign != data.get("sign_string"):
        return jsonify({
            "error": -1,
            "error_note": "Invalid sign"
        })

    return jsonify({
        "click_trans_id": data['click_trans_id'],
        "merchant_trans_id": data['merchant_trans_id'],
        "merchant_confirm_id": "123456",
        "error": 0,
        "error_note": "Payment successful"
    })