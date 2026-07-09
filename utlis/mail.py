from flask_mail import Mail, Message
from flask import render_template

mail = Mail()

def send_booking_email(
    app,
    user_email,
    user_name,
    booking_id,
    salon_name,
    service_name,
    booking_date,
    slot_time,
    amount,
    payment_id,
    salon_address,
    salon_phone
):

    with app.app_context():

        html = render_template(
            "booking_email.html",
            user_name=user_name,
            booking_id=booking_id,
            salon_name=salon_name,
            service_name=service_name,
            booking_date=booking_date,
            slot_time=slot_time,
            amount=amount,
            payment_id=payment_id,
            salon_address=salon_address,
            salon_phone=salon_phone
        )

        msg = Message(
            subject="🎉 GLOOVI Booking Confirmed",
            recipients=[user_email]
        )

        msg.html = html

        mail.send(msg)