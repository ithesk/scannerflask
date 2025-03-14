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
from reportlab.lib.pagesizes import A6, A7
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128, code39, eanbc




def generate_product_label(barcode_number, product_name, price, output_file=None, format="pdf"):
    """
    Genera una etiqueta de producto con código de barras, nombre y precio
    
    Args:
        barcode_number: Código de barras del producto
        product_name: Nombre del producto
        price: Precio del producto
        output_file: Ruta donde guardar la etiqueta (opcional)
        format: Formato de salida ("pdf" o "png")
    
    Returns:
        Ruta al archivo generado o objeto BytesIO si no se especifica archivo
    """
    # Dimensiones en mm (ancho x alto)
    width_mm = 38
    height_mm = 30
    
    # Crear un PDF directamente si se solicita formato PDF
    if format.lower() == "pdf":
        if not output_file:
            output_file = io.BytesIO()
            
        # Crear documento PDF
        doc = SimpleDocTemplate(
            output_file,
            pagesize=(width_mm*mm, height_mm*mm),
            leftMargin=1*mm,
            rightMargin=1*mm,
            topMargin=1*mm,
            bottomMargin=1*mm
        )
        
        # Elementos para el PDF
        elements = []
        
        # Estilos
        styles = getSampleStyleSheet()
        # Estilo para título
        title_style = ParagraphStyle(
            name='Title',
            parent=styles['Normal'],
            fontSize=8,
            leading=9,
            alignment=1  # Centrado
        )
        
        # Estilo para código de barras
        barcode_style = ParagraphStyle(
            name='Barcode',
            parent=styles['Normal'],
            fontSize=6,
            alignment=1  # Centrado
        )
        
        # Estilo para precio
        price_style = ParagraphStyle(
            name='Price',
            parent=styles['Normal'],
            fontSize=12,
            alignment=1,  # Centrado
            fontName='Helvetica-Bold'
        )
        
        # Agregar nombre del producto (truncado si es necesario)
        product_name_short = product_name
        if len(product_name) > 20:
            product_name_short = product_name[:17] + "..."
            
        elements.append(Paragraph(product_name_short, title_style))
        elements.append(Spacer(1, 2*mm))
        
        # Generar código de barras
        try:
            if len(barcode_number) == 13 and barcode_number.isdigit():
                # EAN-13
                barcode = eanbc.Ean13BarcodeWidget(barcode_number, barHeight=10*mm, barWidth=0.18*mm)
            else:
                # Code128
                barcode = code128.Code128(barcode_number, barHeight=10*mm, barWidth=0.18*mm)
                
            drawing = Drawing(width_mm*mm, 12*mm)
            drawing.add(barcode)
            elements.append(drawing)
            
            # Agregar número de código de barras
            elements.append(Paragraph(barcode_number, barcode_style))
            elements.append(Spacer(1, 2*mm))
            
            # Agregar precio
            price_text = f"${price:.2f}"
            elements.append(Paragraph(price_text, price_style))
            
        except Exception as e:
            print(f"Error generando código de barras: {str(e)}")
            elements.append(Paragraph(f"ERROR: {str(e)}", title_style))
        
        # Construir PDF
        doc.build(elements)
        
        if isinstance(output_file, io.BytesIO):
            output_file.seek(0)
            
        return output_file
    
    else:
        # Formato PNG - método anterior
        # Dimensiones fijas (38mm de ancho, altura ajustada para asegurar que se vea todo)
        width_px = int(width_mm * 300 / 25.4)  # 300 DPI
        height_px = int(height_mm * 300 / 25.4)  # 300 DPI
        
        # Crear imagen con fondo blanco
        img = Image.new('RGB', (width_px, height_px), color='white')
        draw = ImageDraw.Draw(img)
        
        # Cargar fuentes (usar tamaños más grandes para mejor legibilidad)
        try:
            # Intentar usar fuentes del sistema
            title_font = ImageFont.truetype("Arial.ttf", 14)
            barcode_font = ImageFont.truetype("Arial.ttf", 10)
            price_font = ImageFont.truetype("Arial.ttf", 16)
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
        
        # Dibujar nombre del producto - centrado
        text_width = title_font.getbbox(product_name_short)[2]
        x_centered = (width_px - text_width) // 2
        draw.text((x_centered, y_pos), product_name_short, font=title_font, fill='black')
        y_pos += 20
        
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
            
            # Pegar el código de barras - centrado
            x_centered = (width_px - barcode_width) // 2
            img.paste(barcode_img, (x_centered, y_pos))
            y_pos += barcode_height + 5
            
            # Dibujar el número del código de barras debajo - centrado
            text_width = barcode_font.getbbox(barcode_number)[2]
            x_centered = (width_px - text_width) // 2
            draw.text((x_centered, y_pos), barcode_number, font=barcode_font, fill='black')
            y_pos += 15
            
            # Dibujar precio - centrado
            price_text = f"${price:.2f}"
            text_width = price_font.getbbox(price_text)[2]
            x_centered = (width_px - text_width) // 2
            draw.text((x_centered, y_pos), price_text, font=price_font, fill='black')
            
        except Exception as e:
            # Si hay algún error generando el código de barras, mostrar un mensaje
            print(f"Error generando código de barras: {str(e)}")
            draw.text((5, y_pos), "ERROR: " + str(e), font=title_font, fill='red')
        
        # Guardar o devolver
        if output_file:
            img.save(output_file, dpi=(300, 300))
            return output_file
        else:
            output = io.BytesIO()
            img.save(output, format='PNG', dpi=(300, 300))
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
        
        # Depuración
        print(f"Imprimiendo etiqueta:")
        print(f"  Archivo: {image_path}")
        print(f"  Impresora: {printer_name}")
        print(f"  Servidor CUPS: {cups_server}")
        
        # Determinar tipo de archivo
        is_pdf = image_path.lower().endswith('.pdf')
        
        # Conexión a CUPS
        if cups_server:
            print(f"Conectando a servidor CUPS remoto: {cups_server}")
            conn = cups.Connection(host=cups_server)
        else:
            print("Conectando a servidor CUPS local")
            conn = cups.Connection()
            
        # Obtener lista de impresoras
        printers = conn.getPrinters()
        print(f"Impresoras disponibles en {cups_server or 'localhost'}: {list(printers.keys())}")
        
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
            raise Exception(f"Impresora '{printer_name}' no encontrada en servidor {cups_server or 'localhost'}")
        
        print(f"Imprimiendo en: {printer_name}")
        
        # Opciones para etiqueta pequeña
        if is_pdf:
            # Opciones para PDF
            options = {
                'media': 'Custom.38x30mm',
                'fit-to-page': 'true',
                'page-left': '0',
                'page-right': '0',
                'page-top': '0',
                'page-bottom': '0'
            }
        else:
            # Opciones para imagen PNG
            options = {
                'media': 'Custom.38x30mm',
                'fit-to-page': 'true',
                'scaling': '100',
                'print-quality': '5',  # Alta calidad
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
    
def generate_and_print(barcode, product_name, price, printer_name=None, cups_server=None, format="pdf"):
    """
    Genera e imprime una etiqueta
    
    Args:
        barcode: Código de barras
        product_name: Nombre del producto
        price: Precio
        printer_name: Nombre de la impresora (opcional)
        cups_server: Servidor CUPS (opcional)
        format: Formato de salida ("pdf" o "png")
    
    Returns:
        True si se imprimió correctamente, False en caso contrario
    """
    try:
        # Depuración
        print(f"generate_and_print llamada con:")
        print(f"  barcode: {barcode}")
        print(f"  product_name: {product_name}")
        print(f"  price: {price}")
        print(f"  printer_name: {printer_name}")
        print(f"  cups_server: {cups_server}")
        print(f"  format: {format}")
        
        # Generar nombre de archivo temporal
        import tempfile
        extension = ".pdf" if format.lower() == "pdf" else ".png"
        temp_file = tempfile.NamedTemporaryFile(suffix=extension, delete=False)
        temp_filename = temp_file.name
        temp_file.close()
        
        print(f"Generando etiqueta temporal: {temp_filename}")
        
        # Generar etiqueta
        generate_product_label(barcode, product_name, price, temp_filename, format)
        
        # Imprimir - asegurarse de pasar cups_server
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