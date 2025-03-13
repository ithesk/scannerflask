# app.py
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import os
import csv
import xmlrpc.client
from collections import Counter
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'odoo_transfer_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'txt'}

# Asegurar que exista el directorio de uploads
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configuración de conexión a Odoo
ODOO_CONFIG = {
    'url': 'http://localhost:8069',
    'db': 'odoo12',
    'username': 'admin',
    'password': 'admin'
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_odoo_locations():
    """Obtener lista de ubicaciones desde Odoo"""
    try:
        # Conexión con Odoo
        common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'], ODOO_CONFIG['password'], {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/object")
        
        # Buscar ubicaciones
        location_ids = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.location', 'search_read',
            [[('usage', '=', 'internal')]], 
            {'fields': ['id', 'name', 'complete_name']}
        )
        
        return location_ids
    except Exception as e:
        print(f"Error al obtener ubicaciones: {str(e)}")
        return []

def create_inventory_transfer(source_location_id, dest_location_id, products_data):
    """
    Crear transferencia interna en Odoo
    
    Args:
        source_location_id: ID de la ubicación origen
        dest_location_id: ID de la ubicación destino
        products_data: diccionario {barcode: quantity}
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Conexión con Odoo
        common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'], ODOO_CONFIG['password'], {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/object")
        
        # Crear picking (transferencia)
        picking_type_ids = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking.type', 'search',
            [[('code', '=', 'internal')]]
        )
        
        if not picking_type_ids:
            return {'success': False, 'message': 'No se encontró tipo de transferencia interna'}
        
        picking_vals = {
            'picking_type_id': picking_type_ids[0],
            'location_id': int(source_location_id),
            'location_dest_id': int(dest_location_id),
            'origin': 'Transferencia desde App Scanner'
        }
        
        picking_id = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking', 'create', [picking_vals]
        )
        
        # Procesar cada producto
        moves_to_create = []
        products_not_found = []
        
        for barcode, qty in products_data.items():
            # Buscar producto por código de barras
            product_ids = models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'product.product', 'search',
                [[('barcode', '=', barcode)]]
            )
            
            if not product_ids:
                products_not_found.append(barcode)
                continue
                
            product_id = product_ids[0]
            
            # Crear movimiento de stock
            move_vals = {
                'name': f'Movimiento de {barcode}',
                'product_id': product_id,
                'product_uom_qty': qty,
                'picking_id': picking_id,
                'location_id': int(source_location_id),
                'location_dest_id': int(dest_location_id),
                'product_uom': 1,  # Unidad de medida por defecto (ajustar si es necesario)
            }
            
            moves_to_create.append(move_vals)
        
        # Crear los movimientos en lote
        if moves_to_create:
            models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.move', 'create', [moves_to_create]
            )
            
            # Confirmar la transferencia
            models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.picking', 'action_confirm', [picking_id]
            )
            
            # Opcional: Marcar como hecho automáticamente
            # models.execute_kw(
            #     ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            #     'stock.picking', 'button_validate', [picking_id]
            # )
            
            result = {
                'success': True,
                'picking_id': picking_id,
                'products_count': len(moves_to_create),
                'products_not_found': products_not_found
            }
        else:
            # Eliminar picking si no hay productos válidos
            models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.picking', 'unlink', [picking_id]
            )
            result = {
                'success': False,
                'message': 'No se encontraron productos válidos',
                'products_not_found': products_not_found
            }
            
        return result
        
    except Exception as e:
        return {'success': False, 'message': str(e)}

@app.route('/')
def index():
    locations = get_odoo_locations()
    return render_template('index.html', locations=locations)

@app.route('/test')
def test():
    return "<h1>La aplicación está funcionando correctamente</h1>"

@app.route('/scan', methods=['POST'])
def process_scan():
    """Procesar los códigos de barras escaneados directamente"""
    source_location = request.form.get('source_location')
    dest_location = request.form.get('dest_location')
    scanned_codes = request.form.get('scanned_codes', '')
    
    if not scanned_codes:
        flash('No se han proporcionado códigos de barras', 'error')
        return redirect(url_for('index'))
    
    # Procesar los códigos escaneados (uno por línea)
    codes_list = [code.strip() for code in scanned_codes.strip().split('\n') if code.strip()]
    products_counter = Counter(codes_list)
    
    # Crear la transferencia
    result = create_inventory_transfer(source_location, dest_location, products_counter)
    
    if result.get('success'):
        flash(f'Transferencia creada con éxito. Se transfirieron {result["products_count"]} productos.', 'success')
        if result.get('products_not_found'):
            flash(f'No se encontraron {len(result["products_not_found"])} productos: {", ".join(result["products_not_found"])}', 'warning')
    else:
        flash(f'Error al crear transferencia: {result.get("message")}', 'error')
    
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    """Procesar archivo CSV subido"""
    if 'file' not in request.files:
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    source_location = request.form.get('source_location')
    dest_location = request.form.get('dest_location')
    
    if file.filename == '':
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Leer el archivo como una sola columna de códigos
            df = pd.read_csv(filepath, header=None, names=['barcode'])
            products_counter = Counter(df['barcode'].tolist())
            
            # Crear la transferencia
            result = create_inventory_transfer(source_location, dest_location, products_counter)
            
            if result.get('success'):
                flash(f'Transferencia creada con éxito. Se transfirieron {result["products_count"]} productos.', 'success')
                if result.get('products_not_found'):
                    flash(f'No se encontraron {len(result["products_not_found"])} productos: {", ".join(result["products_not_found"])}', 'warning')
            else:
                flash(f'Error al crear transferencia: {result.get("message")}', 'error')
                
        except Exception as e:
            flash(f'Error al procesar el archivo: {str(e)}', 'error')
    else:
        flash('Tipo de archivo no permitido', 'error')
    
    return redirect(url_for('index'))

@app.route('/config', methods=['GET', 'POST'])
def config():
    """Página de configuración para los parámetros de Odoo"""
    if request.method == 'POST':
        # Actualizar configuración
        ODOO_CONFIG['url'] = request.form.get('url')
        ODOO_CONFIG['db'] = request.form.get('db')
        ODOO_CONFIG['username'] = request.form.get('username')
        ODOO_CONFIG['password'] = request.form.get('password')
        
        # Probar conexión
        try:
            common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
            uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'], ODOO_CONFIG['password'], {})
            if uid:
                flash('Conexión exitosa a Odoo', 'success')
            else:
                flash('Error de autenticación en Odoo', 'error')
        except Exception as e:
            flash(f'Error de conexión: {str(e)}', 'error')
        
        return redirect(url_for('config'))
    
    return render_template('config.html', config=ODOO_CONFIG)

@app.route('/add_barcode', methods=['POST'])
def add_barcode():
    """API para añadir un código de barras escaneado (para AJAX)"""
    barcode = request.json.get('barcode')
    if barcode:
        return jsonify({'success': True, 'barcode': barcode})
    return jsonify({'success': False, 'message': 'Código de barras no proporcionado'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5010)