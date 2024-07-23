import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import time
import requests
import random

'''
Message formats:

-- Start --
<modifier>:<email target>
<message>
-- End --
    Email addressed to non-saildocs addresses

-- Start --
<message>
-- End --
    Email content is addressed to saildocs. All content will be sent to saildocs

text replacement modifiers:
    {local} -> is replaced with current location (2 d.p.) (Location must be turned on)
    {lat} -> replaced with latitude (int) (Location must be turned on)
    {lon} -> replaced with longitude (int) (Location must be turned on)
'''


'''
Changelog:
- Added degree to allowed_chars
- added new direct saildocs function, which does not require the user to enter query@saildocs.com
    but assumes emails without address to be directed towards saildocs.
'''

# Mail server configuration
MAIL_SERVER = "mail.manitu.de"
EMAIL_ADDRESS = "satellite@yannic-noack.org"
PASSWORD = "Hy^JG>jgZsZWa2@"

# Allowed inReach characters
#ALLOWED_CHARS = """!"#$%\'()*+,-./:;<=>?_¡£¥¿&¤0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÄÅÆÇÉÑØøÜßÖàäåæèéìñòöùüΔΦΓΛΩΠΨΣΘΞ"""
ALLOWED_CHARS = """!"#$%\'()*°+,-./:;<=>?_¡£¥¿&¤0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÄÅÆÇÉÑØøÜßÖàäåæèéìñòöùüΔΦΓΛΩΠΨΣΘΞ"""

class MailHandler:
    def __init__(self):
        self.smtp_server = None
        self.imap_server = None
        print("Connecting to mail servers...")
        self.connect_smtp()
        self.connect_imap()
        print("Connected to mail servers.")

    def connect_smtp(self):
        try:
            self.smtp_server = smtplib.SMTP_SSL(MAIL_SERVER, 465)
            self.smtp_server.login(EMAIL_ADDRESS, PASSWORD)
        except Exception as e:
            print(f"Failed to connect to SMTP server: {e}")
            self.smtp_server = None

    def connect_imap(self):
        try:
            self.imap_server = imaplib.IMAP4_SSL(MAIL_SERVER, 993)
            self.imap_server.login(EMAIL_ADDRESS, PASSWORD)
        except Exception as e:
            print(f"Failed to connect to IMAP server: {e}")
            self.imap_server = None

    def send_message(self, destination, subject, body, attachments=[]):
        if not self.smtp_server:
            self.connect_smtp()
            if not self.smtp_server:
                print("Unable to reestablish SMTP connection.")
                return

        message = self.build_message(destination, subject, body, attachments)
        try:
            self.smtp_server.sendmail(EMAIL_ADDRESS, destination, message.as_string())
        except Exception as e:
            print(f"Failed to send message: {e}")
            self.connect_smtp()
            time.sleep(5)
            self.send_message(destination, subject, body, attachments)

    def search_messages(self, query='UNSEEN'):
        if not self.imap_server:
            self.connect_imap()
            if not self.imap_server:
                print("Unable to reestablish IMAP connection.")
                return []

        try:
            self.imap_server.select("inbox")
            result, data = self.imap_server.search(None, query)
            if result == "OK":
                return data[0].split()
        except Exception as e:
            print(f"Failed to search messages: {e}")
            self.connect_imap()
        return []

    def get_message(self, msg_id):
        if not self.imap_server:
            self.connect_imap()
            if not self.imap_server:
                print("Unable to reestablish IMAP connection.")
                return None

        try:
            self.imap_server.select("inbox")
            result, data = self.imap_server.fetch(msg_id, "(RFC822)")
            if result == "OK":
                return email.message_from_bytes(data[0][1])
        except Exception as e:
            print(f"Failed to fetch message: {e}")
            self.connect_imap()
        return None

    def mark_as_read(self, msg_id):
        if not self.imap_server:
            self.connect_imap()
            if not self.imap_server:
                print("Unable to reestablish IMAP connection.")
                return

        try:
            self.imap_server.select("inbox")
            self.imap_server.store(msg_id, '+FLAGS', r'\Seen')
        except Exception as e:
            print(f"Failed to mark message as read: {e}")
            self.connect_imap()

    def build_message(self, destination, subject, body, attachments=[]):
        message = MIMEMultipart()
        message['From'] = EMAIL_ADDRESS
        message['To'] = destination
        message['Subject'] = subject
        message.attach(MIMEText(body, 'plain'))

        for filename in attachments:
            attachment = open(filename, "rb")
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(filename)}')
            message.attach(part)
            attachment.close()

        return message

def clean_message(message): #Inbound message format processing
    cleaned_message = ''.join([char for char in message if char in ALLOWED_CHARS or char == '\n' or char == ' '])
    try:
        cleaned_message = cleaned_message.split("Thanks for using Saildocs")[0]
    except Exception:
        send_message_to_devices("Cleanup failed. proceeding to send...", "debug@yannic-noack.org")
    return cleaned_message

def segment_message(message): #breaks the message down into usable chunk sizes
    return [message[i:i+155] for i in range(0, len(message), 155)]

def parse_email_content(msg): #???
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                charset = part.get_content_charset()
                body = part.get_payload(decode=True).decode(charset)
    else:
        charset = msg.get_content_charset()
        body = msg.get_payload(decode=True).decode(charset)
    return body

def parse_inreach_email(body): #parse outbound inreach message
    lines = body.split('\n')
    message = ""
    lat = 0.0
    long = 0.0

    #Check if message has an email target or not. If so, save it.
    if "@" in lines[0]: #if an email is contained in the first line, store it
        to_email = lines[0].split(':')[1].strip()

        for line in lines[1:]:
            if 'View the location or send a reply to' in line:
                break
            line = line.strip()
            message += line + '\n'

        message += "\nWhen replying to this email, make sure to remove the previous reply. Satellite messages are costly and having anything unnecessary in them is a waste.\n Thank you!"
    else: #Otherwise assume it goes to saildocs and just call it a day.
        to_email = "query@saildocs.com"

        for line in lines[0:]:
            if 'View the location or send a reply to' in line:
                break
            line = line.strip()
            message += line + '\n'

    return to_email, message.rstrip()

def send_message_to_devices(message_text, from_addr):
    url = "https://share.garmin.com/YNmidFlight/Map/SendMessageToDevices"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://share.garmin.com",
        "Referer": "https://share.garmin.com/ynmidflight",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=0",
        "Te": "trailers"
    }
    data = {
        "deviceIds": "1357850",
        "messageText": message_text,
        "fromAddr": from_addr
    }
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        response_json = response.json()
        if response_json.get("success") == True and response_json.get("result") == {}:
            return "Message sent successfully"
        else:
            return "Failed to send message"
    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"

def process_unread_emails(mail_handler):
    unread_msg_ids = mail_handler.search_messages('UNSEEN')
    for msg_id in unread_msg_ids:
        msg = mail_handler.get_message(msg_id)
        if msg:
            from_email = email.utils.parseaddr(msg['From'])[1]
            subject = msg['Subject']
            body = parse_email_content(msg)
            if from_email == 'no.reply.inreach@garmin.com':
                to_email, message = parse_inreach_email(body)
                print('Received email from inReach to: ' + to_email)
                if to_email and message:
                    mail_handler.send_message(to_email, subject, message)
                else:
                    send_message_to_devices("Failed to parse inReach email content.", "debug@yannic-noack.org")
                    send_message_to_devices(message,"debug@yannic-noack.org")
            else:
                print('Received email from: ' + from_email + ' to inReach')
                cleaned_message = clean_message(body)
                cleaned_message = from_email + "\n" + cleaned_message
                message_parts = segment_message(cleaned_message)
                for idx, part in enumerate(message_parts):
                    print(send_message_to_devices(str(idx) + "\n" + part, "satellite@yannic-noack.org"))
                    time.sleep(3)
            mail_handler.mark_as_read(msg_id)

if __name__ == "__main__":
    mail_handler = MailHandler()
    print("Starting email relay...")
    while True:
        process_unread_emails(mail_handler)
        time.sleep(random.randint(30, 60))
