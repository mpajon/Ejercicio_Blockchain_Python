import datetime
import json

import requests
from flask import render_template, redirect, request

from app import app

# Nodo de la red blockchain con el que nuestra aplicación
# se comunicará para obtener y enviar información
CONNECTED_NODE_ADDRESS = "http://127.0.0.1:8001"

posts = []


def fetch_posts():
    """
    Función para obtener la cadena desde un nodo blockchain,
    procesar la información y almacenarla localmente.
    """
    get_chain_address = "{}/chain".format(CONNECTED_NODE_ADDRESS)
    response = requests.get(get_chain_address)
    if response.status_code == 200:
        content = []        
        chain = json.loads(response.content)  
        for block in chain["chain"]:
            bloque = {}
            bloque['index'] = block["index"]
            bloque['transactions'] = block["transactions"]
            bloque['timestamp'] = block["timestamp"]
            bloque['previous_hash'] = block["previous_hash"]
            bloque['hash'] = block["hash"]
            if 'nonce' in block:
                bloque['nonce'] = block["nonce"]
            content.append(bloque)

        global posts
        posts = sorted(content, key=lambda k: k['timestamp'],
                       reverse=True)


@app.route('/')
def index():
    fetch_posts()
    return render_template('index.html',
                           title='IES Fleming Net: Red descentralizada '
                                 'para compartir información',
                           posts=posts,
                           node_address=CONNECTED_NODE_ADDRESS,
                           readable_time=timestamp_to_string)


@app.route('/submit', methods=['POST'])
def submit_textarea():
    """
    Punto de acceso para crear una nueva transacción vía nuestra
    aplicación.
    """
    post_content = request.form["content"]
    author = request.form["author"]

    post_object = {
        'author': author,
        'content': post_content,
    }

    # Submit a transaction
    new_tx_address = "{}/new_transaction".format(CONNECTED_NODE_ADDRESS)

    requests.post(new_tx_address,
                  json=post_object,
                  headers={'Content-type': 'application/json'})

    return redirect('/')


def timestamp_to_string(epoch_time):
    return datetime.datetime.fromtimestamp(epoch_time).strftime('%d/%m/%Y, %H:%M:%S')
