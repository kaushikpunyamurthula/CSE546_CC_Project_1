# Importing required packages
from flask import Flask
from flask import request, redirect, render_template
import boto3
import configparser
import base64
import logging
import time
import uuid

app = Flask(__name__)
config = configparser.ConfigParser()
config.read('/var/www/html/webtier/configuration.properties')
logging.basicConfig(filename='/var/www/html/webtier/webtier-1.log', level=logging.INFO, filemode="w", 
    format="%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s")

resource_region = config['InstanceSection']['Region']
sqs = boto3.client('sqs', region_name=resource_region)

imageResultMap = {}

@app.route('/face_recognition')
def upload_form():
    return render_template("upload_form.html")

@app.route('/face_recognition/upload', methods=['POST'])
def upload_image():
    global imageResultMap
    files = request.files.getlist('myfile')
    logging.info(str(len(files)) + " Image uploaded")
    queue_url = config['SQSSection']['SQS_Input_Queue_URL']

    def sqs_send(key, data):
        sqs.send_message(
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
                "Image info"
            )
            #MessageDeduplicationId= key,
            #MessageGroupId='cc_1_37'
        )
        
    
    if len(files) == 1 and files[0].filename == '':
        message = 'Please select a file/files before uploading'
        # render_template('upload_form.html', message= message)
        return app.response_class(response=message, status=400)
    else:
        # for file in files:
        file = files[0]
        fileName = file.filename
        #imageResultMap[fileName] = ''
        # Send message to SQS Input Queue
        logging.info("Sending " + fileName + " to SQS Queue")
        encoded_string= str(base64.b64encode(file.read()).decode('utf-8'))
        sqs_send(fileName, encoded_string)
                
            # render_template('upload_form.html', filename=len(files))
            
        while len(imageResultMap) != len(files):
            outputQueueUrl = config['SQSSection']['SQS_Output_Queue_URL']
            response = sqs.receive_message(
                QueueUrl=outputQueueUrl,
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

            try:
                messages = response['Messages']
                message = messages[0]
                outputReceiptHandle = message['ReceiptHandle']
                sqs.delete_message(
                    QueueUrl=outputQueueUrl,
                    ReceiptHandle=outputReceiptHandle
                )
                logging.info("Deleted Message")
                messageAttributes = message['MessageAttributes']
                key = messageAttributes.get('image').get('StringValue')
                output = message['Body']
                instanceId = messageAttributes.get('instance_id').get('StringValue')
                instanceIp = messageAttributes.get('instance_ip').get('StringValue')
                logging.info("Instance Id: " + instanceId + ", Instance Ip: " + instanceIp)
                imageResultMap[key] = output
            except KeyError:
                #logging.info('No messages on the queue!')
                time.sleep(5)
                continue

        logging.info(imageResultMap)
        result = imageResultMap.values()
        imageResultMap = {}
        return app.response_class(response = result, status = 200)

if __name__=="__main__":
    app.run()  
