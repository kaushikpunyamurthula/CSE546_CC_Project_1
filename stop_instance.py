import subprocess
import time
import boto3
import configparser

config = configparser.ConfigParser()
config.read('configuration.properties')

sqs = boto3.client('sqs')
queue_url = config['SQSSection']['SQS_Input_Queue_URL']

def get_queue_length(queue_url) -> int:
    response = sqs.get_queue_attributes(
    QueueUrl=queue_url,
    AttributeNames=[
        'ApproximateNumberOfMessages',
        ]
    )

    queue_length = int(response.get('Attributes').get('ApproximateNumberOfMessages'))
    print(queue_length)
    return queue_length

def process_lookup() -> list:
    process = subprocess.Popen(["ps", "-f", "-u", "ubuntu"], stdout=subprocess.PIPE)
    output = subprocess.Popen(("grep", "image_classification.py"), stdin=process.stdout, stdout=subprocess.PIPE)
    result = output.stdout.readlines()
    process.kill()
    output.kill()
    print("------------------ Running processes ----------------------")
    for r in result:
        print(r.decode("utf-8").rstrip())
    print(len(result))
    return result

def process_poll() -> list:
    result = None
    # TODO: REMOVE
    # poll,  if no process then wait for 3 secs and poll again 
    while True:
        result = process_lookup()
        queue_length = get_queue_length(queue_url)
        if len(result) <= 1 and queue_length == 0:
            print("Sleeping for 10 seconds...")
            time.sleep(10)
            result = process_lookup()
            queue_length = get_queue_length(queue_url)
            if len(result) > 1 or queue_length > 1: continue
            else: return result
        time.sleep(10)
    return result


if __name__ == "__main__":
    result = process_poll()
    queue_length = get_queue_length(queue_url)
    if len(result) <= 1 and queue_length == 0:
        print("Second poll check has no running image classifier... stopping instance. See you later!")

    output = subprocess.check_output(["sudo", "shutdown", "-P", "now"])
    print(output)