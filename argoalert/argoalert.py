from kafka import KafkaConsumer
from requests.auth import HTTPBasicAuth
import json
import requests
import logging
from defusedxml.minidom import parseString
from datetime import datetime
from datetime import timedelta


def parse_timestamp(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")


def date_only_string(dt):
    return dt.strftime("%Y-%m-%d")

def ahead_one_hour(dt):
    return dt + timedelta(hours=1)

def date_to_zulu_string(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def date_days_ago(dt,days):
    return dt - timedelta(days=days)


def date_start_of_day(dt):
    return dt.replace(hour=0, minute=0, second=0)


def date_end_of_day(dt):
    return dt.replace(hour=23, minute=59, second=59)


def ui_group_url(ui_endpoint, report, timestamp, group):
    """Generate an http url to a relevant argo web ui endpoint group timeline page

            Args:
                ui_endpoint: str. Endpoint of designated argo web ui
                report: str. Report name (and not uuid) which is used in argo web ui url path
                timestamp: str. alert Zulu timestamp to construct start_time and end_time
                group: str. alert group name (site / project etc)

            Return:
                str: http url
    """
    start_date = date_only_string(date_days_ago(parse_timestamp(timestamp), 3))
    end_date = date_only_string(parse_timestamp(timestamp))
    return "https://{0}/lavoisier/status_report-site?site={4}&start={2}&end={3}&report={1}&accept=html".format(
        ui_endpoint, report, start_date, end_date, group)


def ui_service_url(ui_endpoint, report, timestamp, group):
    """Generate an http url to a relevant argo web ui service timeline page

            Args:
                ui_endpoint: str. Endpoint of designated argo web ui
                report: str. Report name (and not uuid) which is used in argo web ui url path
                timestamp: str. alert Zulu timestamp to construct start_time and end_time
                group: str. alert group name (site / project etc)

            Return:
                str: http url
    """
    start_date = date_to_zulu_string(date_start_of_day(date_days_ago(parse_timestamp(timestamp), 3)))
    end_date = date_to_zulu_string(ahead_one_hour(parse_timestamp(timestamp)))
    return "https://{0}/lavoisier/status_report-sf?site={4}&start_date={2}&end_date={3}&report={1}&accept=html".format(
        ui_endpoint, report, start_date, end_date, group)


def ui_endpoint_url(ui_endpoint, report, timestamp, group, service):
    """Generate an http url to a relevant argo web ui endpoint timeline page

            Args:
                ui_endpoint: str. Endpoint of designated argo web ui
                report: str. Report name (and not uuid) which is used in argo web ui url path
                timestamp: str. alert Zulu timestamp to construct start_time and end_time
                group: str. alert group name (site / project etc)
                service: str. name of alert affected service

            Return:
                str: http url
    """
    start_date = date_to_zulu_string(date_start_of_day(date_days_ago(parse_timestamp(timestamp), 3)))
    end_date = date_to_zulu_string(ahead_one_hour(parse_timestamp(timestamp)))
    return "http://{0}/lavoisier/status_report-endpoints?site={4}&service={5}&start_date={2}&end_date={3}&report={1}&accept=html".format(
        ui_endpoint, report, start_date, end_date, group, service)



def ui_metric_url(ui_endpoint, report, timestamp, group, service, endpoint):
    """Generate an http url to a relevant argo web ui metric timeline page

        Args:
            ui_endpoint: str. Endpoint of designated argo web ui
            report: str. Report name (and not uuid) which is used in argo web ui url path
            timestamp: str. alert Zulu timestamp to construct start_time and end_time
            group: str. alert group name (site / project etc)
            service: str. name of alert affected service
            endpoint: str. name of alert affected endpoint

        Return:
            str: http url
    """
    start_date = date_to_zulu_string(date_start_of_day(date_days_ago(parse_timestamp(timestamp), 3)))
    end_date = date_to_zulu_string(ahead_one_hour(parse_timestamp(timestamp)))
    return "http://{0}/lavoisier/status_report-metrics?site={4}&service={5}&endpoint={6}&start_date={2}&end_date={3}&report={1}&overview=mod&accept=html".format(
        ui_endpoint, report, start_date, end_date, group, service, endpoint)





def transform(argo_event, environment, grouptype, timeout, ui_endpoint, report):
    """Transform an argo status event to an alerta alert

    Args:
        argo_event: obj. Json representation of an argo status event
        environment: str. Alerta enviroment parameter to build the alert
        grouptype: str. name of top-level grouping type used in this tenant
        timeout: int. Alert timeout in seconds

    Return:
        obj: Json representation of an alerta alert
    """
    status = argo_event["status"].lower()
    hostname = argo_event["hostname"]
    metric = argo_event["metric"]
    group = argo_event["endpoint_group"]
    etype = argo_event["type"]
    service = argo_event["service"]
    ts_monitored = argo_event["ts_monitored"]

    # alerta vars
    resource = ""
    event = etype + "status"
    alerta_service = []
    text = ""

    # update report from event
    if "report" in argo_event:	
	report = argo_event["report"]
	logging.info("update report field from event")

    # prepare alerta attributes
    attributes = {}
    attributes["_group"] = group
    attributes["_service"] = service
    attributes["_endpoint"] = hostname
    attributes["_metric"] = metric
    attributes["_repeat"] = argo_event["repeat"]
    attributes["_ts_monitored"] = ts_monitored
    attributes["_ts_processed"] = argo_event["ts_processed"]

    if etype == "endpoint_group":
        alerta_service.append("endpoint_group")
        resource = group
        text = "[ {0} ] - {1} {0} is {2}".format(group, grouptype, status.upper())
        if ui_endpoint is not "":
            attributes["_alert_url"] = ui_group_url(ui_endpoint, report, ts_monitored, group)
    elif etype == "service":
        alerta_service.append("service")
        resource = group + "/" + service
        text = "[ {0} ] - Service {1} is {2}".format(group, service, status.upper())
        if ui_endpoint is not "":
            attributes["_alert_url"] = ui_service_url(ui_endpoint, report, ts_monitored, group)
    elif etype == "endpoint":
        alerta_service.append("endpoint")
        resource = group + "/" + service + "/" + hostname
        text = "[ {0} ] - Endpoint {1}:{2} is {3}".format(group, hostname, service, status.upper())
        if ui_endpoint is not "":
            attributes["_alert_url"] = ui_endpoint_url(ui_endpoint, report, ts_monitored, group, service)
    elif etype == "metric":
        alerta_service.append("metric")
        resource = group + "/" + service + "/" + hostname + "/" + metric
        text = "[ {0} ] - Metric {1}@({2}:{3}) is {4}".format(group, metric, hostname, service, status.upper())
        if ui_endpoint is not "":
            attributes["_alert_url"] = ui_metric_url(ui_endpoint, report, ts_monitored, group, service, hostname)
    # prepare alerta json
    alerta = {"environment": environment, "event": event, "resource": resource,
              "service": alerta_service, "severity": status, "text": text, "attributes": attributes, "timeout": timeout}

    return alerta


def read_and_send(message, environment, alerta_url, alerta_token, options):
    """Read an argo status event from kafka and send it to alerta

    Args:
        message: str. Current message from kafka queue
        environment: str. Alerta environment to be used (e.g. 'Devel')
        alerta_url: str. Alerta api endpoint
        alerta_token: str. Alerta api access token
        options: dict. Various alert options such as timeout, group type and report name (used in ui links)

    """
    try:
        argo_event = json.loads(message.value)
    except ValueError:
        logging.warning("NOT JSON: " + message.value)
        return

    try:
        alerta = transform(argo_event, environment, options["group_type"], options["timeout"],options ["ui_endpoint"], options["report"])
    except KeyError:
        logging.warning("WRONG JSON SCHEMA: " + message.value)
        return

    logging.info("Attempting to send alert:" + json.dumps(alerta))
    headers = {'Authorization': 'Key ' + alerta_token,
               'Content-Type': 'application/json'}

    r = requests.post(alerta_url + "/alert", headers=headers,
                      data=json.dumps(alerta))

    if r.status_code == 201:
        logging.info("Alert send to alerta successfully")
    else:
        logging.warning("Alert wasn't send to alerta")
        logging.warning(r.text)


def start_listening(environment, kafka_endpoints, kafka_topic,
                    alerta_endpoint, alerta_token, options):
    """Start listening to a kafka topic and send alerts to an alerta endpoint

    Args:
        environment: str. Alerta environment to be used (e.g. 'Devel')
        kafka_endpoints: str. kafka broker endpoint
        kafka_topic: str. kafka topic to listen t
        alerta_endpoint: str. Alerta api endpoint
        alerta_token: str. Alerta api access token
        opts: dict. various alert options such as timeout and group type

    """

    # Initialize kafka
    kafka_list = kafka_endpoints.split(',')

    consumer = KafkaConsumer(kafka_topic,
                             group_id='argo-alerta',
                             bootstrap_servers=kafka_list)
    for message in consumer:
        read_and_send(message, environment, alerta_endpoint, alerta_token, options)


def gocdb_to_contacts(gocdb_xml, use_notif_flag, test_emails):
    """Transform gocdb xml schema info on generic contacts json information

    Args:
        gocdb_xml: str. Data in gocdb xml format
        use_notif_flag: boolean. Examine or not notifications flag when gathering contacts

    Return:
        obj: Json representation of contact information
    """

    xmldoc = parseString(gocdb_xml)
    contacts = []
    clist = xmldoc.getElementsByTagName("CONTACT_EMAIL")
    

    indx = 0
    for item in clist:

	#Check if field is empty
	if item.firstChild == None:
            continue

        # By default accept all contacts
        notify_val = 'Y'
        # If flag on accept only contacts with notification flag
        if use_notif_flag:
	    #check if notification flag exists
            notify = item.parentNode.getElementsByTagName('NOTIFICATIONS')
	    if len(notify)>0:
		# if notification flag is set to false skip
            	notify_val = notify[0].firstChild.nodeValue
	    else:
		continue #notification element not found skip

        if notify_val == 'TRUE' or notify_val == 'Y':
            c = dict()
            c["type"] = item.parentNode.tagName

            # Check if name tag exists
            name_tags = item.parentNode.getElementsByTagName("NAME")
            # if not check short name tag
            if len(name_tags) == 0:
                name_tags = item.parentNode.getElementsByTagName("SHORT_NAME")

            # if still no name related tag skip
            if len(name_tags) == 0:
                continue
            
            c["name"] = name_tags[0].firstChild.nodeValue	    
 
            if test_emails is None:
                c["email"] = item.firstChild.nodeValue
            else:
                c["email"] = test_emails[indx % len(test_emails)]
                indx = indx + 1

            contacts.append(c)

    return contacts


def contacts_to_alerta(contacts, extras):
    """Transform a contacts json object to alerta's rule json object

    Args:
        contacts: obj. Json representation of contact information
        extras: list(str). List of emails to be added as extra recipients

    Return:
        obj: Json representation of alerta mailer rules
    """

    rules = []
    for c in contacts:
        rule_name = "rule_" + c["name"]
        rule_fields = [{u"field": u"resource", u"regex": "^{0}($|\\/)".format(c["name"])}]
        rule_contacts = [c["email"]]
        rule_contacts.extend(extras)
        rule_exclude = True
        rule = {u"name": rule_name, u"fields": rule_fields, u"contacts": rule_contacts, u"exclude": rule_exclude}
        rules.append(rule)

    logging.info("Generated " + str(len(rules)) + " alerta rules from contact information")
    return rules


def get_gocdb(api_url, auth_info, ca_bundle):
    """Http Rest call to gocdb-api to get xml contact information

    Args:
        api_url: str. Gocdb url call
        auth_info: dict. Contains authorization information
        ca_bundle: str. CA bundle file


    Return:
        str: gocdb-api xml response
    """

    verify = False
    if ca_bundle is not None:
        verify = ca_bundle

    logging.info("Requesting data from gocdb api: " + api_url)
    if auth_info["method"] == "cert":
        r = requests.get(api_url, cert=(auth_info["cert"], auth_info["key"]), verify=verify)
    else:
        r = requests.get(api_url, auth=HTTPBasicAuth(auth_info["user"], auth_info["pass"]), verify=verify)

    if r.status_code == 200:
        logging.info("Gocdb data retrieval successful")
        return r.text.encode('utf-8').strip()

    return ""


def write_rules(rules, outfile):
    """Writes alerta email rules to a specific output file

    Args:
        rules: obj. json representation of alerta rules
        outfile: str. output filename path
    """

    json_str = json.dumps(rules, indent=4)
    logging.info("Saving rule to file: " + outfile)
    with open(outfile, "w") as output_file:
        output_file.write(json_str)
