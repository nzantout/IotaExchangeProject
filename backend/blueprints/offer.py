from flask import Blueprint, abort, request, jsonify
from typing import List
import jwt
from ..app import db
from ..model.offer import Offer, offer_schema, offers_schema
from ..model.transaction_request import TransactionRequest, transaction_requests_schema, transaction_request_schema
from ..model.transaction import Transaction, transaction_schema, transactions_schema
from ..helpers.authentication import create_token, extract_auth_token, decode_token, authenticate
from sqlalchemy.orm import joinedload

offer_blueprint = Blueprint('offer_blueprint', __name__)
offers_blueprint = Blueprint('offers_blueprint', __name__)


@offers_blueprint.route('/', methods=['GET'])
def get_offers():
    user_id, is_teller = authenticate()
    transaction_request_id = request.args.get('request-id', default=None)
    if is_teller:
        if transaction_request_id is not None:
            transaction_request: TransactionRequest = TransactionRequest.query.filter_by(id=transaction_request_id).options(
                joinedload(TransactionRequest.offers)
            ).first()
            if transaction_request is None:
                abort(400)
            for offer in transaction_request.offers:
                if offer.teller_id != user_id:
                    offer.teller_id = None
            return jsonify(transaction_request_schema.dump(transaction_request))
        else:
            transaction_requests: List[TransactionRequest] = TransactionRequest.query\
                .join(TransactionRequest.offers).filter(Offer.teller_id == user_id).all()
            return jsonify(transaction_request_schema.dump(transaction_requests))
    else:
        transaction_request: TransactionRequest = TransactionRequest.query.filter_by(id=transaction_request_id).options(
            joinedload(TransactionRequest.offers)
        ).first()
        if transaction_request is None:
            abort(400)
        return jsonify(transaction_request_schema.dump(transaction_request))


@offer_blueprint.route('/', methods=['POST'])
def post_offer():
    user_id, is_teller = authenticate()
    if not is_teller:
        abort(403)
    try:
        transaction_request: TransactionRequest = TransactionRequest.query.filter_by(id=request.json['transaction_id'])\
            .first()
        if transaction_request is None:
            abort(400)
        transaction_request.num_offers += 1
        offer = Offer(
            amount=float(request.json['amount']),
            transaction_id=request.json['transaction_id'],
            teller_id=user_id,
        )
        db.session.add(offer)
        db.commit()
    except ValueError:
        abort(400)
    except KeyError:
        abort(400)


@offer_blueprint.route('/', methods=['DELETE'])
def delete_offer():
    user_id, is_teller = authenticate()
    if not is_teller:
        abort(403)
    offer_id = request.args.get('offer-id')
    offer = Offer.query.filter_by(id=offer_id).first()
    if offer is None:
        abort(400)
    db.session.delete(offer)
    db.session.commit()
    return jsonify(offer_schema.dump(offer))


@offer_blueprint.route('/accept', methods=['POST'])
def accept_offer():
    user_id, is_teller = authenticate()
    if is_teller:
        abort(403)
    try:
        offer: Offer = Offer.query.filter_by(id=request.json['offer_id']).first()
        if offer is None:
            abort(400)
        transaction_id = offer.transaction_id
        transaction_request: TransactionRequest = TransactionRequest.query.filter_by(id=transaction_id).first()
        usd_to_lbp = transaction_request.usd_to_lbp
        transaction = Transaction(
            usd_to_lbp=usd_to_lbp,
            usd_amount=transaction_request.amount if usd_to_lbp else offer.amount,
            lbp_amount=offer.amount if usd_to_lbp else transaction_request.amount,
            teller_id=user_id,
            user_id=transaction_request.user_id
        )
        db.session.add(transaction)
        db.session.commit()
        Offer.query.filter_by(transaction_id=transaction_id).delete()
        TransactionRequest.query.filter_by(id=transaction_id).delete()
        db.session.commit()
        return jsonify(offer_schema.dump(offer))
    except KeyError:
        abort(400)


@offer_blueprint.route('/reject', methods=['POST'])
def reject_offer():
    user_id, is_teller = authenticate()
    if is_teller:
        abort(403)
    try:
        offer: Offer = Offer.query.filter_by(id=request.json['offer_id']).first()
        if offer is None:
            abort(400)
        transaction_request: TransactionRequest = TransactionRequest.query.filter_by(id=offer.transaction_id)\
            .first()
        transaction_request.num_offers -= 1
        db.session.delete(offer)
        db.session.commit()
        return jsonify(offer_schema.dump(offer))
    except KeyError:
        abort(400)