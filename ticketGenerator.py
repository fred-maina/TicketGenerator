import json
import boto3
from PIL import Image, ImageDraw, ImageFont
import qrcode
from datetime import datetime
import uuid
from io import BytesIO

# Initialize clients
s3_client = boto3.client('s3')
ses_client = boto3.client('ses')
bucket_name = 'eventsticket'  # Replace with your S3 bucket name

def generate_qr_code(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill="black", back_color="white")

    qr_img = qr_img.convert("RGB")
    draw = ImageDraw.Draw(qr_img)
    font = ImageFont.truetype("arial.ttf", 24)
    text = "Scan Me"

    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    text_position = ((qr_img.width - text_width) // 2, qr_img.height - text_height - 10)
    draw.text(text_position, text, font=font, fill="blue")

    return qr_img

def create_ticket(event_name, event_date, buyer_name, ticket_code, purchase_time, payment_mode, ticket_type, ticket_price, qr_code):
    ticket_width, ticket_height = 1400, 1900  # Increased size for better spacing
    ticket = Image.new("RGB", (ticket_width, ticket_height), "#ffffff")
    draw = ImageDraw.Draw(ticket)

    header_font = ImageFont.truetype("arial.ttf", 60)
    detail_font = ImageFont.truetype("arial.ttf", 34)
    bold_font = ImageFont.truetype("arial.ttf", 40)

    draw.rectangle([(0, 0), (ticket_width, 180)], fill="#2E86C1")
    draw.text((ticket_width // 2, 90), event_name, font=header_font, fill="white", anchor="mm")

    y_offset = 220
    line_spacing = 80
    draw.line([(50, y_offset - 20), (ticket_width - 50, y_offset - 20)], fill="#B3B6B7", width=2)

    details = [
        ("Event Date", event_date),
        ("Buyer Name", buyer_name),
        ("Ticket Code", ticket_code),
        ("Purchase Time", purchase_time),
        ("Payment Mode", payment_mode),
        ("Ticket Type", ticket_type),
        ("Ticket Price", ticket_price),
    ]

    for label, value in details:
        draw.text((100, y_offset), f"{label}:", font=bold_font, fill="#333333")
        draw.text((500, y_offset), value, font=detail_font, fill="#555555")
        y_offset += line_spacing

    draw.line([(50, y_offset), (ticket_width - 50, y_offset)], fill="#B3B6B7", width=2)
    y_offset += 40

    qr_code = qr_code.resize((700, 700))  # Larger QR code
    qr_code_position = (ticket_width // 2 - qr_code.width // 2, y_offset)
    ticket.paste(qr_code, qr_code_position)

    y_offset += 740

    draw.text((ticket_width // 2, y_offset), "Please present this ticket at entry.", font=bold_font, fill="#FF5733", anchor="mm")

    y_offset += 60
    draw.text((ticket_width // 2, y_offset), "Thank you for purchasing!", font=bold_font, fill="#FF5733", anchor="mm")

    y_offset += 80
    contact_text = "For refunds or rescheduling, contact support@eventify.com"
    draw.text((ticket_width // 2, y_offset), contact_text, font=detail_font, fill="#999999", anchor="mm")

    return ticket

def send_ticket_email(to_email, ticket_url):
    subject = "Your Event Ticket"
    body = f"Dear User,\n\nThank you for purchasing a ticket for the event. Please find your ticket below:\n\n{ticket_url}\n\nBest regards,\nEventify Team"

    # Send email through SES
    response = ses_client.send_email(
        Source='your-sender-email@example.com',  # Replace with your SES verified email address
        Destination={
            'ToAddresses': [to_email],
        },
        Message={
            'Subject': {'Data': subject},
            'Body': {'Text': {'Data': body}},
        }
    )
    return response

def lambda_handler(event):
    try:
        # Input from Spring Boot or API Gateway (you can pass these parameters)
        event_name = event["event_name"]
        event_date = event["event_date"]
        buyer_name = event["buyer_name"]
        ticket_code = event["ticket_code"]
        payment_mode = event["payment_mode"]
        ticket_type = event["ticket_type"]
        ticket_price = event["ticket_price"]
        purchase_time = event["purchase_time"]

        # Generate QR code
        qr_code = generate_qr_code(ticket_code)

        # Generate the ticket
        ticket = create_ticket(event_name, event_date, buyer_name, ticket_code, purchase_time, payment_mode, ticket_type, ticket_price, qr_code)

        # Save ticket to in-memory file
        ticket_buffer = BytesIO()
        ticket.save(ticket_buffer, format="PNG")
        ticket_buffer.seek(0)

        # Generate a unique file name (UUID)
        file_name = f"tickets/{str(uuid.uuid4())}.png"

        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=ticket_buffer,
            ContentType='image/png',
            ACL='public-read'  # Adjust ACL as needed
        )

        # Generate the public URL for the ticket
        public_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"

        # Return the public URL to Spring Boot backend
        return {
            'statusCode': 200,
            'body': json.dumps({'ticket_url': public_url})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
