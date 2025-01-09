from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import uuid
import os
from functools import wraps
from dotenv import load_dotenv
import requests
from sqlalchemy import desc

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///invoices.db'  # Puede cambiarse a MySQL/PostgreSQL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo para gestión de tokens
class ExternalToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(500), nullable=False)
    refresh_token = db.Column(db.String(500), nullable=False)
    fecha_generacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)

    @classmethod
    def get_active_token(cls):
        return cls.query.filter_by(activo=True).order_by(desc(cls.fecha_generacion)).first()

# Modelos
class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ruc = db.Column(db.String(11), unique=True, nullable=False)
    razon_social = db.Column(db.String(200), nullable=False)
    direccion = db.Column(db.String(200))
    email = db.Column(db.String(120))
    facturas = db.relationship('Factura', backref='cliente', lazy=True)

class Factura(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    fecha_emision = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    total = db.Column(db.Float, nullable=False)
    igv = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(20), default='GENERADA')
    items = db.relationship('ItemFactura', backref='factura', lazy=True)

class ItemFactura(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('factura.id'), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

def obtener_token_vigente():
    """
    Verifica si existe un token vigente o solicita uno nuevo si es necesario
    """
    token_actual = ExternalToken.get_active_token()
    
    # Verificar si necesitamos un nuevo token
    if token_actual is None or \
       datetime.utcnow() - token_actual.fecha_generacion > timedelta(minutes=55):
        return solicitar_nuevo_token()
    
    return token_actual.token

def solicitar_nuevo_token():
    """
    Solicita un nuevo token al API externa
    """
    try:
        # Configuración para la solicitud
        headers = {
            'Authorization': f'Bearer {app.config["EXTERNAL_API_KEY"]}',
            'Content-Type': 'application/json'
        }
        
        # Realizar solicitud al API externa
        response = requests.post(
            app.config['EXTERNAL_API_URL'],
            headers=headers,
            json={'grant_type': 'client_credentials'}
        )
        
        if response.status_code == 200:
            # Desactivar tokens anteriores
            ExternalToken.query.update({ExternalToken.activo: False})
            
            # Crear nuevo registro de token
            nuevo_token = ExternalToken(
                token=response.json()['access_token'],
                fecha_generacion=datetime.utcnow(),
                activo=True
            )
            
            db.session.add(nuevo_token)
            db.session.commit()
            
            return nuevo_token.token
        else:
            raise Exception(f"Error al obtener token: {response.status_code}")
            
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Error en la solicitud del token: {str(e)}")


# Rutas para Clientes
@app.route('/api/clientes', methods=['POST'])
def crear_cliente():
    data = request.get_json()
    nuevo_cliente = Cliente(
        ruc=data['ruc'],
        razon_social=data['razon_social'],
        direccion=data.get('direccion'),
        email=data.get('email')
    )
    try:
        db.session.add(nuevo_cliente)
        db.session.commit()
        return jsonify({'mensaje': 'Cliente creado exitosamente', 'id': nuevo_cliente.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/clientes', methods=['GET'])
def obtener_clientes():
    clientes = Cliente.query.all()
    return jsonify([{
        'id': c.id,
        'ruc': c.ruc,
        'razon_social': c.razon_social,
        'direccion': c.direccion,
        'email': c.email
    } for c in clientes])

# Rutas para Facturas
@app.route('/api/nueva/factura', methods=['POST'])
def crear_nueva_factura():
    data = request.get_json()
    
    # Generar número de factura único
    numero_factura = f"F{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    
    nueva_factura = Factura(
        numero=numero_factura,
        cliente_id=data['cliente_id'],
        total=data['total'],
        igv=data['total'] * 0.18  # 18% IGV
    )
    
    try:
        db.session.add(nueva_factura)
        
        # Agregar items de la factura
        for item in data['items']:
            nuevo_item = ItemFactura(
                factura=nueva_factura,
                descripcion=item['descripcion'],
                cantidad=item['cantidad'],
                precio_unitario=item['precio_unitario'],
                subtotal=item['cantidad'] * item['precio_unitario']
            )
            db.session.add(nuevo_item)
        
        db.session.commit()
        return jsonify({
            'mensaje': 'Factura creada exitosamente',
            'numero_factura': numero_factura
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

# Rutas para Facturas
@app.route('/api/facturas', methods=['POST'])
def crear_factura():
    data = request.get_json()
    
    # Generar número de factura único
    numero_factura = f"F{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    
    nueva_factura = Factura(
        numero=numero_factura,
        cliente_id=data['cliente_id'],
        total=data['total'],
        igv=data['total'] * 0.18  # 18% IGV
    )
    
    try:
        db.session.add(nueva_factura)
        
        # Agregar items de la factura
        for item in data['items']:
            nuevo_item = ItemFactura(
                factura=nueva_factura,
                descripcion=item['descripcion'],
                cantidad=item['cantidad'],
                precio_unitario=item['precio_unitario'],
                subtotal=item['cantidad'] * item['precio_unitario']
            )
            db.session.add(nuevo_item)
        
        db.session.commit()
        return jsonify({
            'mensaje': 'Factura creada exitosamente',
            'numero_factura': numero_factura
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/facturas/<numero>', methods=['GET'])
def obtener_factura(numero):
    factura = Factura.query.filter_by(numero=numero).first()
    if not factura:
        return jsonify({'error': 'Factura no encontrada'}), 404
    
    return jsonify({
        'numero': factura.numero,
        'fecha_emision': factura.fecha_emision.isoformat(),
        'cliente': {
            'id': factura.cliente.id,
            'ruc': factura.cliente.ruc,
            'razon_social': factura.cliente.razon_social
        },
        'total': factura.total,
        'igv': factura.igv,
        'estado': factura.estado,
        'items': [{
            'descripcion': item.descripcion,
            'cantidad': item.cantidad,
            'precio_unitario': item.precio_unitario,
            'subtotal': item.subtotal
        } for item in factura.items]
    })

@app.route('/api/facturas/<numero>/anular', methods=['POST'])
def anular_factura(numero):
    factura = Factura.query.filter_by(numero=numero).first()
    if not factura:
        return jsonify({'error': 'Factura no encontrada'}), 404
    
    factura.estado = 'ANULADA'
    try:
        db.session.commit()
        return jsonify({'mensaje': 'Factura anulada exitosamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run('127.0.0.1', port=5000, debug=True)