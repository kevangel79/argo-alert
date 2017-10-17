from kafka import KafkaConsumer
import json
import requests
import logging
from xml.dom import minidom


def transform(argo_event, environment):
    """Transform an argo status event to an alerta alert

    Args:
        argo_event: obj. Json representation of an argo status event
        environment: str. Alerta enviroment parameter to build the alert

    Return:
        obj: Json representation of an alerta alert
    """
    status = argo_event["status"].lower()
    hostname = argo_event["hostname"]
    metric = argo_event["metric"]
    group = argo_event["endpoint_group"]
    etype = argo_event["type"]
    service = argo_event["service"]

    # alerta vars
    resource = ""
    event = "status"
    alerta_service = []

    if etype == "endpoint_group":
        alerta_service.append("endpoint_group")
        resource = group
    elif etype == "service":
        alerta_service.append("service")
        resource = group + "/" + service
    elif etype == "endpoint":
        alerta_service.append("endpoint")
        resource = group + "/" + service + "/" + hostname
    elif etype == "metric":
        alerta_service.append("metric")
        resource = group + "/" + service + "/" + hostname + "/" + metric
    # prepare alerta json
    alerta = {"environment": environment, "event": event, "resource": resource,
              "service": alerta_service, "severity": status}

    return alerta


def read_and_send(message, environment, alerta_url, alerta_token):
    """Read an argo status event from kafka and send it to alerta

    Args:
        message: str. Current message from kafka queue
        environment: str. Alerta environment to be used (e.g. 'Devel')
        alerta_url: str. Alerta api endpoint
        alerta_token: str. Alerta api access token

    """
    try:
        argo_event = json.loads(message.value)
    except ValueError:
        logging.warning("NOT JSON: " + message.value)
        return

    try:
        alerta = transform(argo_event, environment)
    except KeyError:
        logging.warning("WRONG JSON SCHEMA: " + message.value)
        return

    logging.info("Attempting to send alert:" + json.dumps(alerta))
    headers = {'Authorization': 'Key ' + alerta_token}
    r = requests.post(alerta_url + "/alert", headers=headers,
                      data=json.dumps(alerta))
    if r.status_code == 201:
        logging.info("Alert send to alerta succesfully")
    else:
        logging.warning("Alert wasn't send to alerta")
        logging.warning(r.text)


def start_listening(environment, kafka_endpoint, kafka_topic,
                    alerta_endpoint, alerta_token):
    """Start listening to a kafka topic and send alerts to an alerta endpoint

    Args:
        environment: str. Alerta environment to be used (e.g. 'Devel')
        log_level: str. logging level (e.g. 'INFO', 'WARNING', 'ERROR')
        kafka_endpoint: str. kafka broker endpoint
        kafka_topic: str. kafka topic to listen t
        alerta_endpoint: str. Alerta api endpoint
        alerta_token: str. Alerta api access token

    """


    # Initialize kafka
    consumer = KafkaConsumer(kafka_topic,
                             group_id='argo-group',
                             bootstrap_servers=[kafka_endpoint])
    for message in consumer:
        read_and_send(message, environment, alerta_endpoint, alerta_token)

def gocdb_to_contacts(gocdb_xml):
    """Transform gocdb xml schema info on generic contacts json information

    Args:
        gocdb_xml: str. Data in gocdb xml format

    Return:
        obj: Json representation of contact information
    """
    xmldoc = minidom.parseString(gocdb_xml)
    contacts = []
    clist = xmldoc.getElementsByTagName("CONTACT_EMAIL")
    for item in clist:
        c = {}
        c["type"] = item.parentNode.tagName
        c["name"] = item.parentNode.getAttribute("NAME")
        c["email"] = item.firstChild.nodeValue
        contacts.append(c)

    logging.info("Extracted " + str(len(clist)) + " contacts from gocdb xml")
    return contacts


def contacts_to_alerta(contacts):
    """Transform a contacts json object to alerta's rule json object

    Args:
        contacts: obj. Json representation of contact information

    Return:
        obj: Json representation of alerta mailer rules
    """
    rules = []
    for c in contacts:

        rule_name = "rule_" + c["name"]
        rule_fields = [ {u"field": u"resource", u"regex": c["name"]} ]
        rule_contacts = [ c["email"] ]
        rule_exlude = True
        rule = {u"name":rule_name,u"fields":rule_fields,u"contacts":rule_contacts,u"exclude":rule_exlude}
        rules.append(rule)

    logging.info("Generated " + str(len(rules)) + " alerta rules from contact information")
    return rules


def get_gocdb(api_url,ca_bundle,hostcert,hostkey,verify):
    """Http Rest call to gocdb-api to get xml contact information

    Args:
        url: str. Gocdb url call
        ca_bundle: str. CA bundle file
        cert: str. Host certificate file
        key: str. Host key file

    Return:
        str: gocdb-api xml response
    """

    verf = False
    if verify==True:
        verf = ca_bundle

    logging.info("Requesting data from gocdb api: " + api_url)
    r = requests.get(api_url,cert=(hostcert,hostkey),verify=verf)

    if r.status_code == 200:
        logging.info("Gocdb data retrieval succesfull")
        return r.text.encode('utf-8').strip()


    return ""

def write_rules(rules,outfile):
    """Writes alerta email rules to a specific output file

    Args:
        riles: obj. json representation of alerta rules
        outfile: str. output filename path
    """

    jsonStr = json.dumps(rules,indent=4)
    logging.info("Saving rule to file: " + outfile)
    with open(outfile, "w") as output_file:
        output_file.write(jsonStr)

