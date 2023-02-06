import os
import sys
import signal
import atexit
from hashlib import sha256
import json
import time

from flask import Flask, request
import requests

class Block:
    def __init__(self, index, transactions, timestamp, previous_hash,nonce=0):
        """
        Constructor de la clase `Block`.
        :param index: ID único del bloque.
        :param transactions: Lista de transacciones.
        :param timestamp: Momento en que el bloque fue generado.
        """
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce
    def compute_hash(self):
        """
        Convierte el bloque en una cadena JSON y luego retorna el hash
        del mismo.
        """
        # La cadena equivalente también considera el nuevo campo previous_hash,
        # pues self.__dict__ devuelve todos los campos de la clase.
        block_string = json.dumps(self.__dict__, sort_keys=True)
        return sha256(block_string.encode()).hexdigest()

class Blockchain:
    # Dificultad del algoritmo de prueba de trabajo.
    difficulty = 3

    def __init__(self, chain=None):
        self.unconfirmed_transactions = []
        self.chain = chain
        if self.chain is None:
            self.chain = []
            self.create_genesis_block()

    def create_genesis_block(self):
        """
        Una función para generar el bloque génesis y añadirlo a la
        cadena. El bloque tiene index 0, previous_hash 0 y un hash
        válido.
        """
        genesis_block = Block(0, [], 0, "0")
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        """
        Una forma rápida y pythonica de retornar el bloque más reciente de la cadena.
        Nótese que la cadena siempre contendrá al menos un último bloque (o sea,
        el bloque génesis).
        """
        return self.chain[-1]

    @staticmethod
    def proof_of_work(block):
        """
        Función que intenta distintos valores de nonce hasta obtener
        un hash que satisfaga nuestro criterio de dificultad.
        """
        block.nonce = 0
 
        computed_hash = block.compute_hash()
        while not computed_hash.startswith('0' * Blockchain.difficulty):
            block.nonce += 1
            computed_hash = block.compute_hash()
 
        return computed_hash

    def add_block(self, block, proof):
        """
        Una función que agrega el bloque a la cadena luego de la verificación.
        La verificación incluye:
        * Comprobar que la prueba es válida.
        * El valor del hash previo del bloque coincide con el hash del último
          bloque de la cadena.
        """
        previous_hash = self.last_block.hash
        
        if previous_hash != block.previous_hash:
            return False
        
        if not self.is_valid_proof(block, proof):
            return False
        
        block.hash = proof
        self.chain.append(block)
        
    @classmethod
    def is_valid_proof(self, block, block_hash):
        """
        Conmprobar si block_hash es un hash válido y satisface nuestro
        criterio de dificultad.
        """
        return (block_hash.startswith('0' * Blockchain.difficulty) and
                block_hash == block.compute_hash())

    def add_new_transaction(self, transaction):
        self.unconfirmed_transactions.append(transaction)
 
    def mine(self):
        """
        Esta función sirve como una interfaz para añadir las transacciones
        pendientes al blockchain añadiéndolas al bloque y calculando la
        prueba de trabajo.
        """
        if not self.unconfirmed_transactions:
            return False
            
        last_block = self.last_block
        new_block = Block(index=last_block.index + 1,
                      transactions=self.unconfirmed_transactions,
                      timestamp=time.time(),
                      previous_hash=last_block.hash)
        proof = self.proof_of_work(new_block)
        self.add_block(new_block, proof)
    
        self.unconfirmed_transactions = []
        return True

    @classmethod
    def check_chain_validity(cls, chain):
        result = True
        previous_hash = "0"

        for block in chain:
            block_hash = block.hash
            # remove the hash field to recompute the hash again
            # using `compute_hash` method.
            delattr(block, "hash")

            if not cls.is_valid_proof(block, block_hash) or \
                    previous_hash != block.previous_hash:
                result = False
                break

            block.hash, previous_hash = block_hash, block_hash

        return result

# Inicializar la aplicación Flask
app =  Flask(__name__)
 
# Inicializar el objeto blockchain.
blockchain = None
peers = set()

chain_file_name = os.environ.get('DATA_FILE')

@app.route('/new_transaction', methods=['POST'])
def new_transaction():
    tx_data = request.get_json()
    required_fields = ["author", "content"]
 
    for field in required_fields:
        if not tx_data.get(field):
            return "Invalid transaction data", 404
 
    tx_data["timestamp"] = time.time()
 
    blockchain.add_new_transaction(tx_data)
 
    return "Success", 201

@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json.dumps({"length": len(chain_data),
                       "chain": chain_data,
                       "peers": list(peers)})

@app.route('/mine', methods=['GET'])
def mine_unconfirmed_transactions():
    result = blockchain.mine()
    if not result:
        return "No hay transacciones para minar"
    else:
        # Making sure we have the longest chain before announcing to the network
        chain_length = len(blockchain.chain)
        consensus()
        if chain_length == len(blockchain.chain):
            # announce the recently mined block to the network
            announce_new_block(blockchain.last_block)
        return "Se ha realizado el minado de un nuevo bloque con los mensajes pendientes"

@app.route('/pending_tx')
def get_pending_tx():
    return json.dumps(blockchain.unconfirmed_transactions)

# Punto de acceso para añadir nuevos compañeros a la red.
@app.route('/register_node', methods=['POST'])
def register_new_peers():
    # La dirección del nodo compañero.
    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    # Añadir el nodo a la lista de compañeros.
    peers.add(node_address)

    # Retornar el blockhain al nuevo nodo registrado para que pueda sincronizar.
    return get_chain()

@app.route('/register_with', methods=['POST'])
def register_with_existing_node():
    """
    Internamente llama al punto de acceso `/register_node`
    para registrar el nodo actual con el nodo remoto especificado
    en la petición, y sincronizar el blockchain asimismo con el
    nodo remoto. 
    """
    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    data = {"node_address": request.host_url}
    headers = {'Content-Type': "application/json"}

    # Hacer una petición para registrarse en el nodo remoto y obtener
    # información.
    response = requests.post(node_address + "/register_node",
                             data=json.dumps(data), headers=headers)

    if response.status_code == 200:
        global blockchain
        global peers
        # Actualizar la cadena y los compañeros.
        chain_dump = response.json()['chain']
        blockchain = create_chain_from_dump(chain_dump)
        peers.update(response.json()['peers'])
        return "Registration successful ", 200
    else:
        # si algo sale mal, pasárselo a la respuesta de la API
        return response.content, response.status_code

# punto de acceso para añadir un bloque minado por alguien más a la cadena del nodo.
@app.route('/add_block', methods=['POST'])
def verify_and_add_block():
    block_data = request.get_json()
    block = Block(block_data["index"],
                  block_data["transactions"],
                  block_data["timestamp"],
                  block_data["previous_hash"],
                  block_data["nonce"])
 
    proof = block_data['hash']
    try:
        blockchain.add_block(block, proof)
    except ValueError as e:
        return "El bloque ha sido descartado por el nodo: " + e.str(), 400
 
    return "Block added to the chain", 201

def create_chain_from_dump(chain_dump):
    generated_blockchain = Blockchain()
    for idx, block_data in enumerate(chain_dump):
        if idx == 0:
            continue  # skip genesis block
        block = Block(block_data["index"],
                      block_data["transactions"],
                      block_data["timestamp"],
                      block_data["previous_hash"],
                      block_data["nonce"])
        proof = block_data['hash']
        generated_blockchain.add_block(block, proof)
    return generated_blockchain

def save_chain():
    if chain_file_name is not None:
        with open(chain_file_name, 'w') as chain_file:
            chain_file.write(get_chain())

def exit_from_signal(signum, stack_frame):
    sys.exit(0)

def announce_new_block(block):
    for peer in peers:
        url = "{}add_block".format(peer)
        headers = {'Content-Type': "application/json"}
        requests.post(url,
                      data=json.dumps(block.__dict__, sort_keys=True),
                      headers=headers)

def consensus():
    """
    Nuestro simple algoritmo de consenso. Si una cadena válida más larga es
    encontrada, la nuestra es reemplazada por ella.
    """
    global blockchain
 
    longest_chain = None
    current_len = len(blockchain.chain)
 
    for node in peers:
        response = requests.get('{}chain'.format(node))
        length = response.json()['length']
        chain = response.json()['chain']
        if length > current_len and blockchain.check_chain_validity(chain):
            current_len = length
            longest_chain = chain
 
    if longest_chain:
        blockchain = longest_chain
        return True
 
    return False

# Uncomment this line if you want to specify the port number in the code
#app.run(debug=True, port=8000)

atexit.register(save_chain)
signal.signal(signal.SIGTERM, exit_from_signal)
signal.signal(signal.SIGINT, exit_from_signal)

if chain_file_name is None:
    data = None
else:
    with open(chain_file_name, 'r') as chain_file:
        raw_data = chain_file.read()
        if raw_data is None or len(raw_data) == 0:
            data = None
        else:
            data = json.loads(raw_data)

if data is None:
    # the node's copy of blockchain
    blockchain = Blockchain()
else:
    blockchain = create_chain_from_dump(data['chain'])
    peers.update(data['peers'])