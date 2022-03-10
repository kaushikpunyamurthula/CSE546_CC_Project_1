# Importing required packages
from flask import Flask
from flask import request, redirect, render_template
import boto3
import configparser
import base64
import logging

app = Flask(__name__)
config = configparser.ConfigParser()
config.read('/var/www/html/webtier/configuration.properties')
logging.basicConfig(filename='/var/www/html/webtier/webtier.log', level=logging.INFO, filemode="w")

# This is the route for the default User interface page with all the thee buttons
@app.route('/image_classifier')
def upload_form():
    return render_template("image_upload.html")


# This is request hadler route where the image uploads are sent to backend using a post request
@app.route('/image_classifier', methods=['POST'])
def upload_image():
    #Files are all accessed using the request object
    files = request.files.getlist('photos')
    logging.info(str(len(files)) + " Image(s) uploaded")
    # Intializing S3 bucket name and client and resource objects for S3 and SQS 
    # Used to connect to the services
    resource_region = config['InstanceSection']['Region']
    sqs = boto3.client('sqs', region_name=resource_region)
    # Input sqs queue url
    queue_url = config['SQSSection']['SQS_Input_Queue_URL']

    # These are the conditions for different buttons in the form
    # If the user clicks on upload button then it exceutes the below code
    # It checks weather the the user has selected atleast one image 
    # If user selects multiple images then it takes all the images and uploads to S3 and messages to sqs with attributes 
    if request.form['action'] == 'Upload':
       # This function is to send messages to sqs queue with the image attributes
        def sqs_send(key, data):
            
            response = sqs.send_message(
                QueueUrl=queue_url,
                
                MessageAttributes={
                    'image_name':{ 
                    'DataType': 'String',
                    'StringValue': key
                        },
                    'image':{ 
                    'DataType': 'String',
                    'StringValue': data
                        }
                },
                MessageBody=(
                "Image info "
                ),
                MessageDeduplicationId= key,
                MessageGroupId='cc_1_37'
            )
        # This is for chcking atleast one image is selected or not, if not then message is shown to the user
        if len(files)== 1 and files[0].filename == '':
            message = 'Please select a file/files before uploading'
            return render_template('image_upload.html', message= message)
        else:
            for file in files:
                filename = file.filename
                # Send message to SQS queue
                logging.info("Sending " + filename + " to SQS Queue")
                encoded_string= str(base64.b64encode(file.read()).decode('utf-8'))
                sqs_send(filename, encoded_string)
            return render_template('image_upload.html', filename=len(files))
    else:
        # This else is for result button 
        # It intially gets the approximate images in the queue which is queue length and processes all the messages
        # Shows results in the UI
        
        queue_url = config['SQSSection']['SQS_Output_Queue_URL']
        # Get approximate number of messages
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                'ApproximateNumberOfMessages',
            ]
        )

        results = []
        # Receive message from SQS queue
        # Get the message count
        msg_count = response.get('Attributes').get('ApproximateNumberOfMessages')
        # Retrive all the messages and send them to the User interface
        for i in range(int(msg_count)):
            response = sqs.receive_message(
                QueueUrl=queue_url,
                AttributeNames=[
                    'SentTimestamp'
                ],
                MaxNumberOfMessages=1,
                MessageAttributeNames=[
                    'All'
                ],
                    VisibilityTimeout=30,
                    WaitTimeSeconds=0  
            )
            logging.info("Received Message")
            message = response['Messages'][0]
            receipt_handle = message['ReceiptHandle']
            sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            logging.info("Deleted Message")
            results.append(message['Body'])        
        
        return render_template('image_upload.html', results=results)


if __name__=="__main__":
    app.run()  
