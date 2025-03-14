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
    # Dimensiones (38mm de ancho, ajustable en altura)
    width = 38 * mm
    height = 20 * mm  # Altura estimada, ajustaremos según el contenido
    
    # Crear imagen
    img = Image.new('RGB', (int(width), int(height)), color='white')
    draw = ImageDraw.Draw(img)
    
    # Cargar fuentes (usar fuentes del sistema o incluir en el proyecto)
    try:
        title_font = ImageFont.truetype("Arial.ttf", 12)
        normal_font = ImageFont.truetype("Arial.ttf", 9)
        price_font = ImageFont.truetype("Arial.ttf", 14)
    except IOError:
        # Si no encuentra las fuentes, usar fuentes por defecto
        title_font = ImageFont.load_default()
        normal_font = ImageFont.load_default()
        price_font = ImageFont.load_default()
    
    # Agregar nombre del producto
    product_name_short = product_name
    if len(product_name) > 20:
        product_name_short = product_name[:17] + "..."
    
    draw.text((2, 2), product_name_short, font=title_font, fill='black')
    
    # Calcular y dibujar código de barras
    barcode_io = io.BytesIO()
    code = barcode.get('ean13', barcode_number, writer=ImageWriter())
    code.write(barcode_io)
    
    barcode_img = Image.open(barcode_io)
    # Redimensionar código de barras para ajustar al ancho
    barcode_width = int(width - 4)
    barcode_height = int(barcode_width * barcode_img.height / barcode_img.width)
    barcode_img = barcode_img.resize((barcode_width, barcode_height))
    
    # Pegar código de barras
    y_position = 20
    img.paste(barcode_img, (2, y_position))
    
    # Agregar precio
    y_position += barcode_height + 5
    price_text = f"${price:.2f}"
    draw.text((2, y_position), price_text, font=price_font, fill='black')
    
    # Redimensionar imagen a la altura correcta
    new_height = y_position + 25
    img = img.crop((0, 0, int(width), new_height))
    
    # Guardar o devolver
    if output_file:
        img.save(output_file)
        return output_file
    else:
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

def print_label(image_path, printer_name=None):
    """
    Imprime una etiqueta usando CUPS
    
    Args:
        image_path: Ruta a la imagen de la etiqueta
        printer_name: Nombre de la impresora (opcional, usa la predeterminada si no se especifica)
    
    Returns:
        ID del trabajo de impresión
    """
    try:
        conn = cups.Connection()
        printers = conn.getPrinters()
        
        if not printer_name:
            # Usar la impresora predeterminada
            printer_name = conn.getDefault()
            if not printer_name:
                # Si no hay impresora predeterminada, usar la primera disponible
                if printers:
                    printer_name = list(printers.keys())[0]
                else:
                    raise Exception("No hay impresoras disponibles")
        
        # Verificar que la impresora existe
        if printer_name not in printers:
            raise Exception(f"Impresora '{printer_name}' no encontrada")
        
        # Opciones de impresión para etiquetas pequeñas
        options = {
            'media': '38x20mm',  # Tamaño de la etiqueta
            'fit-to-page': 'True',
            'scaling': '100'
        }
        
        # Imprimir
        job_id = conn.printFile(printer_name, image_path, "Etiqueta de producto", options)
        return job_id
    
    except Exception as e:
        print(f"Error al imprimir: {str(e)}")
        return None

def generate_and_print(barcode, product_name, price, printer_name=None):
    """
    Genera e imprime una etiqueta
    
    Args:
        barcode: Código de barras
        product_name: Nombre del producto
        price: Precio
        printer_name: Nombre de la impresora (opcional)
    
    Returns:
        True si se imprimió correctamente, False en caso contrario
    """
    try:
        # Generar nombre de archivo temporal
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_filename = temp_file.name
        temp_file.close()
        
        # Generar etiqueta
        generate_product_label(barcode, product_name, price, temp_filename)
        
        # Imprimir
        job_id = print_label(temp_filename, printer_name)
        
        # Limpiar archivos temporales
        os.unlink(temp_filename)
        
        return job_id is not None
    
    except Exception as e:
        print(f"Error al generar e imprimir etiqueta: {str(e)}")
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