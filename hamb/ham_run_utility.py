from pprint import pprint
from datetime import datetime
import yaml
import pandas as pd
from cocore.Logger import Logger
from cocore.config import Config
from collections import OrderedDict
from sqlalchemy import create_engine
import uuid

CONF = Config()
LOG = Logger()
KEY_PREFIX = "dq"


class HandlerEngine(object):
    """

    """

    def run(self, manifest, result, file_location=None):
        """
        in this step we read test_result
        import and run appropriate handler(s)
        :return:
        """
        LOG.l("\n---------------------------\nhandlers")
        level = result["summary"]["status"]
        LOG.l("handler level: " + level)
        config = self.get_handler_config(manifest, level, file_location)

        print(
            "\n---------------------------\noverall results for: "
            + manifest
            + "\n"
        )
        pprint(result["START SUMMARY"])
        print("SUMMARY:")
        pprint(result["summary"])
        print("\n" + "SUCCESSES:" + "\n")
        pprint(result["success detail"])
        print("FAILS:" + "\n")
        pprint(result["fail detail"])
        print("\n")
        pprint(result["table"])
        print("\n")

        # service specific handlers
        for handler in config:
            print(f"handler: {handler}")
            LOG.l("executing handler: " + list(handler.keys())[0])
            test_module = f"hamb.handlers.{list(handler.keys())[0]}"
            print(test_module)
            mod = __import__(test_module, fromlist=["Handler"])
            class_ = getattr(mod, "Handler")
            class_(CONF).setup().run(result, list(handler.values())[0])

    @staticmethod
    def get_handler_config(service, level, file_location=None):
        """

        :param manifest:
        :return:
        """
        handler_config = None
        if not file_location:
            file_location = "services.yaml"
        with open(file_location, "r") as services_yaml:
            try:
                obj = yaml.safe_load(services_yaml)
            except Exception as e:
                LOG.l_exception(f"issue parsing yaml: {e}")
                exit(1)
            if service in obj:
                handler_config = obj[service][level]
            else:
                handler_config = obj["default"][level]
        return handler_config


class TestEngine(object):
    """
    main entry point for ham_run
    """

    def run(self, manifest):
        """

        :param manifest:
        :return:
        """
        status = None
        passed_cnt = 0
        warning_cnt = 0
        failed_cnt = 0
        # this will be the core data model
        # result= {
        #     'START SUMMARY': [],
        #     'summary': {},
        #     'new output': {},
        #     'success detail': [],
        #     'fail detail': []
        # }

        result = OrderedDict()
        result["START SUMMARY"] = (
            "**************************************\
            ***************************************\
            ***************************************\
            ***************************************\
            ************************"
            "**************************************\
            ***************************************\
            ***************************************\
            ***************************************\
            ************************"
        )
        result["table"] = {}
        result["summary"] = {}
        result["fail detail"] = []
        result["success detail"] = []

        test_config = self.manifest_reader(manifest)
        print("test_config", test_config)
        job = []
        stat = []
        diff = []
        for test, test_conf in test_config.items():
            test_module = f'hamb.{test_conf["type"].lower()}'
            mod = __import__(test_module, fromlist=["SqlCompare"])
            try:
                class_ = getattr(mod, "SqlCompare")
            except Exception as e:
                LOG.l_exception(
                    f"module not present or issue in module import: {e}"
                )
                exit(1)

            status, detail = class_(test_conf).setup(CONF).run()

            if status == "success":
                passed_cnt += 1
            elif status == "warning":
                warning_cnt += 1
            else:
                failed_cnt += 1

            if status == "success":
                result["success detail"].insert(0, detail)
                diff.append(" ")
            elif status == "warning":
                result["success detail"].append(detail)
                diff.append(detail["diff"])
            else:
                result["fail detail"].append(detail)
                diff.append(detail["diff"])

            job.append(detail["test"])
            stat.append(detail["status"])
            LOG.l(status)
            LOG.l(detail)

            # add to database
            try:
                engine = create_engine(CONF["hamb"]["database"])
                idnum = uuid.uuid1()
                engine.execute(
                    """
                INSERT INTO public.hamb_history
                (manifest, test, status, source_connection, "source count",
                target_connection, "target count", diff, warning_threshold,
                failure_threshold, environment, created_time, uuid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        manifest,
                        test,
                        status,
                        test_conf["conn_a"],
                        detail["result_a"],
                        test_conf["conn_b"],
                        detail["result_b"],
                        detail["diff"],
                        test_conf["warning_threshold"],
                        test_conf["failure_threshold"],
                        CONF["hamb"]["environment"],
                        datetime.now(),
                        idnum,
                    ),
                )
            except Exception as e:
                print(f"cannot write results to database: {e}")

        if failed_cnt > 0:
            overall_status = "failure"
        elif warning_cnt > 0:
            overall_status = "warning"
        else:
            overall_status = "success"

        result["summary"] = {
            "status": overall_status,
            "failed_count": failed_cnt,
            "warning_cnt": warning_cnt,
            "passed_cnt": passed_cnt,
            "exec_time": str(datetime.now()),
            "manifest": manifest,
        }
        table = {"Job": job, "Status": stat, "Diff": diff}
        result["table"] = pd.DataFrame(
            data=table, columns=("Job", "Status", "Diff")
        )

        return result

    @staticmethod
    def manifest_reader(manifest, file_location=None):
        """

        :param manifest:
        :return:
        """
        if not file_location:
            file_location = "manifests/%s.yaml"
        with open(file_location % manifest, "r") as checklist_yaml:
            try:
                test_config = yaml.safe_load(checklist_yaml)
            except Exception as e:
                LOG.l_exception(f"issue parsing yaml, please check: {e}")
        return test_config


def json_serializer(data):
    """
    JSON serializer for objects not serializable by default json code"
    :param obj:
    :return:
    """
    if isinstance(data, datetime):
        serial = data.isoformat()
        return serial
    raise TypeError("Type not serializable")
