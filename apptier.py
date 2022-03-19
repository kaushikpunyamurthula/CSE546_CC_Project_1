import boto3 
import os
import time
import subprocess
import configparser
import logging
import base64
from ec2_metadata import ec2_metadata

config = configparser.ConfigParser()
config.read('/home/ec2-user/configuration.properties')
logging.basicConfig(filename='/home/ec2-user/apptier.log', level=logging.INFO, 
    format="%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s", filemode='w')

resource_region = config['InstanceSection']['Region']
s3 = boto3.resource('s3', region_name = resource_region)
sqs = boto3.client('sqs', region_name = resource_region)
inputQueueName = config['SQSSection']['SQS_Input_Queue_Name']
inputQueueUrl = config['SQSSection']['SQS_Input_Queue_URL']
outputQueueUrl = config['SQSSection']['SQS_Output_Queue_URL']

passCounter = 0
isImageProcessed = False

def sqsReceiveMessage(inputQueueUrl):
    # Listen to Input Queue
    logging.info("Starting SQS Listener")
    response = sqs.receive_message(
        QueueUrl=inputQueueUrl,
        AttributeNames=[
            'SentTimestamp'
        ],
        MaxNumberOfMessages=1,
        MessageAttributeNames=[
            'All'
        ],
        VisibilityTimeout=60
    )
    return response.get('Messages', [None])[0]

while True:
    logging.info("Receiving Messages")
    message = sqsReceiveMessage(inputQueueUrl)
    if message:
        # Get image data from SQS input queue and Write to file
        messageAttributes = message['MessageAttributes']
        logging.info(messageAttributes)
        inputReceiptHandle = message['ReceiptHandle']
        requestId = messageAttributes.get('request_id').get('StringValue')
        imageName = messageAttributes.get('image_name').get('StringValue')
        imageData = messageAttributes.get('image_data').get('StringValue')
        logging.info(imageName)
        imageFile = open(imageName, 'wb')
        imageFile.write(base64.b64decode(imageData))
        imageFile.close()
        imageFile = open(imageName, 'rb')

        # Upload image file to S3 input bucket
        inputBucketName = config['S3Section']['S3_Input_Bucket_Name']
        s3.Bucket(inputBucketName).put_object(Key = imageName, Body = imageFile)
        imageFile.close()

        # Run face recognition on image file
        logging.info("Face Recognition on image: " + imageName)
        output = subprocess.check_output(['python3', 'face_recognition.py', imageName])
        person = output.decode("utf-8").rstrip()
        outputContent = "Image : " + imageName + ", Person: " + person
        logging.info(outputContent)

        # Write output to text file and Upload to S3 output bucket
        fileName = imageName.split('.')[0]
        outputBucketName = config['S3Section']['S3_Output_Bucket_Name']
        outputFileName =  fileName + ".txt"
        s3.Object(outputBucketName, outputFileName).put(Body=outputContent)
        logging.info("Uploaded output file: " + outputFileName + " to S3 Output Bucket")

        isImageProcessed = True

        # Send output to SQS output queue
        send_response = sqs.send_message(
            QueueUrl=outputQueueUrl,
            MessageAttributes={
                'request_id': {
                    'DataType': 'String',
                    'StringValue': requestId
                },
                'image_name':{ 
                    'DataType': 'String',
                    'StringValue': imageName
                },
                'output':{ 
                    'DataType': 'String',
                    'StringValue': outputContent
                },
                'instance_id':{ 
                    'DataType': 'String',
                    'StringValue': ec2_metadata.instance_id
                },
                'instance_ip':{ 
                    'DataType': 'String',
                    'StringValue': ec2_metadata.public_ipv4
                }
            },
            MessageBody=person
        )
        logging.info("Message " + str(send_response.get('MessageId')) + " Sent to Output Queue Successfully.")

        # Delete processed Message from SQS input queue
        sqs.delete_message(
            QueueUrl=inputQueueUrl,
            ReceiptHandle=inputReceiptHandle
        )
        logging.info("Message Deleted from Input Queue Successfully.")
        if os.path.exists(imageName):
            os.remove(imageName)
    
    if passCounter == 60:
        break
    elif not isImageProcessed:
        passCounter += 1
        time.sleep(1)
    else:
        isImageProcessed = False
        passCounter= 0

# Stop Instance after checking queue is empty for 60 seconds
logging.info("Stopping Instance")
output = subprocess.check_output(["sudo", "shutdown", "-P", "now"])
logging.info(output)
