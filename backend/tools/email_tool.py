import resend
import os

resend.api_key = os.environ.get("RESEND_API_KEY")

def send_email(email_content,email_id):
    try:
        attachments = []
        for  filepath in email_content['attachments']:
            if not os.path.exists(filepath):
                continue
            with open(filepath,"rb") as f:        #read in bytes bec csv/doxs not in plain text
                attachments.append({
                    "filename":os.path.basename(filepath), #get -- cleaned.csv , employee.csv etc type
                    "content":list(f.read())      #list--converts them into the format Resend's API expects
                })
 
        resend.Emails.send({
            "from": "TazzaCode AI <onboarding@resend.dev>",
            "to": [email_id],
            "subject": email_content["subject"],
            "text": email_content["body"],
            "attachments": attachments
         })

        return {"success": True}

    except:
        return {"success": False}
