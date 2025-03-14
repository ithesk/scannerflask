# report_generator.py
import csv
import os
import json
from collections import Counter
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def get_product_data_from_odoo(barcodes, odoo_connection_func):
    """
    Obtiene los nombres y detalles de productos desde Odoo usando códigos de barras.
    
    Args:
        barcodes: lista de códigos de barras a buscar.
        odoo_connection_func: función para obtener conexión a Odoo.
    
    Returns:
        dict: Diccionario de datos de productos {barcode: {name, default_code, etc}}.
    """
    uid, models = odoo_connection_func()
    if not uid or not models:
        return {}
    
    # Buscar productos por códigos de barras en lotes para evitar límites XML-RPC
    products_data = {}
    batch_size = 20
    
    # Crear lista con códigos de barras únicos
    unique_barcodes = list(set(barcodes))
    
    for i in range(0, len(unique_barcodes), batch_size):
        batch = unique_barcodes[i:i+batch_size]
        
        # Construir el dominio de búsqueda de forma correcta
        if len(batch) > 1:
            # Se anteponen (n-1) operadores OR al inicio
            domain = ['|'] * (len(batch) - 1) + [('barcode', '=', str(barcode)) for barcode in batch]
        else:
            domain = [('barcode', '=', str(batch[0]))]
        
        try:
            # Se vuelve a obtener la conexión en cada iteración (según la configuración actual)
            uid, models = odoo_connection_func()
            if not uid or not models:
                continue
                
            # Obtener la configuración global desde un archivo config.json
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            products = models.execute_kw(
                config['db'], uid, config['password'],
                'product.product', 'search_read',
                [domain],
                {'fields': ['name', 'barcode', 'default_code', 'list_price', 'qty_available']}
            )
            
            # Organizar productos por código de barras
            for product in products:
                if product.get('barcode'):
                    products_data[product['barcode']] = product
                    
        except Exception as e:
            print(f"Error al buscar productos en lote {i//batch_size + 1}: {str(e)}")
    
    return products_data

def analyze_csv_file(filepath):
    """
    Analiza un archivo CSV con códigos de barras y cuenta la frecuencia.
    
    Args:
        filepath: ruta del archivo CSV.
        
    Returns:
        Counter: diccionario con conteos de cada código de barras.
    """
    barcodes = []
    
    with open(filepath, 'r', encoding='utf-8') as csvfile:
        try:
            # Intentar primero leer como CSV estructurado con encabezado
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                first_column_value = next(iter(row.values()))
                if first_column_value:
                    barcodes.append(str(first_column_value).strip())
        except Exception:
            # Si falla, se reinicia el archivo y se lee de forma simple
            csvfile.seek(0)
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                if row and row[0].strip():
                    barcodes.append(str(row[0]).strip())
    
    # En caso de que se tenga una sola línea con muchos códigos concatenados
    if len(barcodes) == 1 and len(barcodes[0]) > 20:
        long_barcode = barcodes[0]
        barcode_length = 13
        barcodes = [long_barcode[i:i+barcode_length] for i in range(0, len(long_barcode), barcode_length)]
    
    # Contar frecuencias
    barcode_counter = Counter(barcodes)
    
    return barcode_counter

def generate_pdf_report(barcode_counter, product_data, output_filename):
    """
    Genera un reporte PDF con la información de productos y cantidades
    
    Args:
        barcode_counter: diccionario con conteos de códigos de barras
        product_data: datos de productos desde Odoo
        output_filename: nombre del archivo PDF a generar
    """
    # Crear documento PDF
    pdf_path = os.path.abspath(output_filename)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Crear un estilo personalizado para la tabla
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ])
    
    # Títulos
    elements.append(Paragraph(f"Reporte de Inventario", title_style))
    elements.append(Spacer(1, 0.25*inch))
    elements.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Paragraph(f"Total de productos diferentes: {len(barcode_counter)}", normal_style))
    elements.append(Paragraph(f"Total de unidades: {sum(barcode_counter.values())}", normal_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Función para truncar texto largo
    def truncate_text(text, max_length=35):
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text
    
    # Crear tabla de datos
    data = [["Código de Barras", "Nombre del Producto", "Cantidad", "Precio"]]
    
    # Productos encontrados
    found_products = []
    total_value = 0
    
    # Agregar productos con información completa
    for barcode, count in barcode_counter.items():
        if barcode in product_data:
            product = product_data[barcode]
            name = product.get('name', 'Desconocido')
            price = product.get('list_price', 0.0)
            total_item_value = price * count
            total_value += total_item_value
            
            found_products.append(barcode)
            data.append([
                barcode, 
                truncate_text(name), 
                str(count), 
                f"${price:.2f}"
            ])
    
    # Agregar productos no encontrados
    not_found = [barcode for barcode in barcode_counter.keys() if barcode not in product_data]
    if not_found:
        data.append(["", "", "", ""])
        data.append(["PRODUCTOS NO ENCONTRADOS EN ODOO", "", "", ""])
        for barcode in not_found:
            count = barcode_counter[barcode]
            data.append([barcode, "NO ENCONTRADO", str(count), "$0.00"])
    
    # Crear tabla con anchos de columna específicos
    table = Table(data, colWidths=[1.5*inch, 3.7*inch, 0.5*inch, 0.7*inch])
    table.setStyle(table_style)
    
    elements.append(table)
    
    # Agregar totales
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(f"Total de productos encontrados: {len(found_products)} de {len(barcode_counter)}", normal_style))
    elements.append(Paragraph(f"Valor total del inventario: ${total_value:.2f}", subtitle_style))
    
    # Construir PDF
    doc.build(elements)
    
    return pdf_path

def create_inventory_report(csv_file, odoo_connection_func, output_filename="inventory_report.pdf"):
    """
    Función principal para crear el reporte completo.
    
    Args:
        csv_file: ruta al archivo CSV de códigos de barras.
        odoo_connection_func: función para obtener conexión a Odoo.
        output_filename: nombre del archivo PDF de salida.
    
    Returns:
        String: ruta al archivo PDF generado.
    """
    try:
        print(f"Analizando archivo CSV: {csv_file}")
        barcode_counter = analyze_csv_file(csv_file)
        
        print(f"Se encontraron {len(barcode_counter)} códigos de barras únicos")
        print(f"Total de unidades: {sum(barcode_counter.values())}")
        
        print("Obteniendo información de productos desde Odoo...")
        product_data = get_product_data_from_odoo(barcode_counter.keys(), odoo_connection_func)
        
        print(f"Se encontraron {len(product_data)} productos en Odoo")
        
        print(f"Generando reporte PDF: {output_filename}")
        pdf_path = generate_pdf_report(barcode_counter, product_data, output_filename)
        
        print(f"Reporte generado exitosamente: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        print(f"Error al generar reporte: {str(e)}")
        raise e
