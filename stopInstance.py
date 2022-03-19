import subprocess
import time
import boto3
import configparser
import logging

config = configparser.ConfigParser()
config.read('./configuration.properties')
logging.basicConfig(filename='/home/ec2-user/apptier.log', level=logging.INFO, 
    format="%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s", filemode='w')

sqs = boto3.client('sqs')
inputQueueUrl = config['SQSSection']['SQS_Input_Queue_URL']

def getQueueLength(inputQueueUrl) -> int:
    response = sqs.get_queue_attributes(
    QueueUrl=inputQueueUrl,
    AttributeNames=[
        'ApproximateNumberOfMessages',
        ]
    )

    queueLength = int(response.get('Attributes').get('ApproximateNumberOfMessages'))
    
    return queueLength

def killProcesses():
    process = subprocess.Popen(["ps", "-ef"], stdout=subprocess.PIPE)
    output = subprocess.Popen(("grep", "face_recognition.py"), stdin=process.stdout, stdout=subprocess.PIPE)
    result = output.stdout.readlines()
    output.kill()
    process.kill()
    logging.info("------------------ Running processes ----------------------")
    for r in result:
        logging.info(r.decode("utf-8").rstrip())
    logging.info(len(result))
    return result

def checkProccess():
    result = None
    # TODO: REMOVE
    # poll,  if no process then wait for 3 secs and poll again 
    while True:
        result = killProcesses()
        queue_length = getQueueLength(inputQueueUrl)
        if len(result) <= 1 and queue_length == 0:
            logging.info("Sleeping for 10 seconds...")
            time.sleep(10)
            result = killProcesses()
            queue_length = getQueueLength(inputQueueUrl)
            if len(result) > 1 or queue_length > 1: continue
            else: return result
        time.sleep(10)
    return result

if __name__ == "__main__":
    result = checkProccess()
    queue_length = getQueueLength(inputQueueUrl)
    if len(result) <= 1 and queue_length == 0:
        logging.info("Second poll check has no running image classifier... stopping instance. See you later!")

        #output = subprocess.check_output(["sudo", "shutdown", "-P", "now"])
        #logging.info(output)
