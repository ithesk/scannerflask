import io
import os
import cups
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm
from reportlab.graphics import renderPM
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import Drawing

def generate_product_label(barcode_number, product_name, price, output_file=None):
    """
    Genera una etiqueta de producto con código de barras, nombre y precio
    
    Args:
        barcode_number: Código de barras del producto
        product_name: Nombre del producto
        price: Precio del producto
        output_file: Ruta donde guardar la etiqueta (opcional)
    
    Returns:
        Ruta al archivo generado o objeto BytesIO si no se especifica archivo
    """
    # Dimensiones fijas (38mm de ancho, altura ajustada para asegurar que se vea todo)
    width_mm = 38
    height_mm = 30  # Aumentado para asegurar que todo sea visible
    
    # Convertir mm a píxeles (a 300 DPI para alta calidad)
    dpi = 300
    width_px = int(width_mm * dpi / 25.4)
    height_px = int(height_mm * dpi / 25.4)
    
    # Crear imagen con fondo blanco
    img = Image.new('RGB', (width_px, height_px), color='white')
    draw = ImageDraw.Draw(img)
    
    # Cargar fuentes (usar tamaños más pequeños para caber en 38mm)
    try:
        # Intentar usar fuentes del sistema
        title_font = ImageFont.truetype("Arial.ttf", 10)
        barcode_font = ImageFont.truetype("Arial.ttf", 8)
        price_font = ImageFont.truetype("Arial.ttf", 12)
    except IOError:
        # Si no encuentra las fuentes, usar fuentes por defecto
        title_font = ImageFont.load_default()
        barcode_font = ImageFont.load_default()
        price_font = ImageFont.load_default()
    
    # Agregar nombre del producto (truncado si es necesario)
    product_name_short = product_name
    if len(product_name) > 20:
        product_name_short = product_name[:17] + "..."
    
    # Posicionamiento vertical
    y_pos = 5
    
    # Dibujar nombre del producto
    draw.text((5, y_pos), product_name_short, font=title_font, fill='black')
    y_pos += 15
    
    # Generar y dibujar código de barras
    try:
        # Usar python-barcode para generar un código de barras EAN-13 o CODE128
        if len(barcode_number) == 13 and barcode_number.isdigit():
            code = barcode.get('ean13', barcode_number, writer=ImageWriter())
        else:
            code = barcode.get('code128', barcode_number, writer=ImageWriter())
            
        # Guardar a BytesIO
        barcode_io = io.BytesIO()
        code.write(barcode_io)
        barcode_io.seek(0)
        
        # Cargar como imagen PIL
        barcode_img = Image.open(barcode_io)
        
        # Redimensionar al ancho de etiqueta, manteniendo proporción
        barcode_width = width_px - 10  # Dejar margen
        barcode_height = int(barcode_width * barcode_img.height / barcode_img.width)
        barcode_img = barcode_img.resize((barcode_width, barcode_height))
        
        # Pegar el código de barras
        img.paste(barcode_img, (5, y_pos))
        y_pos += barcode_height + 5
        
        # Dibujar el número del código de barras debajo
        draw.text((5, y_pos), barcode_number, font=barcode_font, fill='black')
        y_pos += 12
        
        # Dibujar precio
        price_text = f"${price:.2f}"
        draw.text((5, y_pos), price_text, font=price_font, fill='black')
        
    except Exception as e:
        # Si hay algún error generando el código de barras, mostrar un mensaje
        print(f"Error generando código de barras: {str(e)}")
        draw.text((5, y_pos), "ERROR: " + str(e), font=title_font, fill='red')
    
    # Guardar o devolver
    if output_file:
        img.save(output_file, dpi=(dpi, dpi))
        return output_file
    else:
        output = io.BytesIO()
        img.save(output, format='PNG', dpi=(dpi, dpi))
        output.seek(0)
        return output

def print_label(image_path, printer_name=None, cups_server=None):
    """
    Imprime una etiqueta usando CUPS
    
    Args:
        image_path: Ruta a la imagen de la etiqueta
        printer_name: Nombre de la impresora (opcional, usa la predeterminada si no se especifica)
        cups_server: Servidor CUPS (opcional, usa localhost si no se especifica)
    
    Returns:
        ID del trabajo de impresión o None si hay error
    """
    try:
        import cups
        
        # Conexión a CUPS
        if cups_server:
            print(f"Conectando a servidor CUPS: {cups_server}")
            conn = cups.Connection(host=cups_server) 
        else:
            print("Conectando a servidor CUPS local")
            conn = cups.Connection()
        
        # Obtener lista de impresoras
        printers = conn.getPrinters()
        print(f"Impresoras disponibles: {list(printers.keys())}")
        
        # Si no se especifica impresora, usar la predeterminada
        if not printer_name:
            printer_name = conn.getDefault()
            print(f"Impresora predeterminada: {printer_name}")
            
            # Si no hay predeterminada, usar la primera disponible
            if not printer_name and printers:
                printer_name = list(printers.keys())[0]
                print(f"Usando primera impresora disponible: {printer_name}")
        
        # Verificar que la impresora existe
        if printer_name not in printers:
            raise Exception(f"Impresora '{printer_name}' no encontrada")
        
        print(f"Imprimiendo en: {printer_name}")
        
        # Opciones para etiqueta pequeña
        options = {
            # Especificar tamaño exacto de etiqueta
            'media': 'Custom.38x30mm',
            # Asegurar que la imagen se ajuste a la etiqueta
            'fit-to-page': 'true',
            'scaling': '100',
            # Calidad de impresión
            'print-quality': '5',  # Alta calidad
            # Sin márgenes
            'page-left': '0',
            'page-right': '0',
            'page-top': '0',
            'page-bottom': '0'
        }
        
        print(f"Opciones de impresión: {options}")
        
        # Imprimir archivo
        job_id = conn.printFile(
            printer_name,
            image_path,
            "Etiqueta de producto",
            options
        )
        
        print(f"Trabajo de impresión enviado, ID: {job_id}")
        return job_id
        
    except Exception as e:
        print(f"Error al imprimir: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    
def generate_and_print(barcode, product_name, price, printer_name=None, cups_server=None):
    """
    Genera e imprime una etiqueta
    
    Args:
        barcode: Código de barras
        product_name: Nombre del producto
        price: Precio
        printer_name: Nombre de la impresora (opcional)
        cups_server: Servidor CUPS (opcional)
    
    Returns:
        True si se imprimió correctamente, False en caso contrario
    """
    try:
        # Generar nombre de archivo temporal
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_filename = temp_file.name
        temp_file.close()
        
        print(f"Generando etiqueta temporal: {temp_filename}")
        
        # Generar etiqueta
        generate_product_label(barcode, product_name, price, temp_filename)
        
        # Imprimir
        job_id = print_label(temp_filename, printer_name, cups_server)
        
        # Limpiar archivos temporales (después de un tiempo para asegurar que se imprimió)
        import threading
        def cleanup():
            import time, os
            time.sleep(10)  # Esperar 10 segundos antes de eliminar
            try:
                os.unlink(temp_filename)
                print(f"Archivo temporal eliminado: {temp_filename}")
            except:
                pass
                
        threading.Thread(target=cleanup).start()
        
        return job_id is not None
        
    except Exception as e:
        print(f"Error al generar e imprimir etiqueta: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# Ejemplo de uso
if __name__ == "__main__":
    # Generar una etiqueta de ejemplo
    barcode = "4657465784172"
    product_name = "Sample Text"
    price = 19.99
    
    # Generar y guardar
    output_file = "sample_label.png"
    generate_product_label(barcode, product_name, price, output_file)
    print(f"Etiqueta guardada en: {output_file}")
    
    # Para imprimir:
    # success = generate_and_print(barcode, product_name, price)
    # if success:
    #     print("Etiqueta impresa correctamente")
    # else:
    #     print("Error al imprimir etiqueta")