"""
here is where the slack handler will go
"""
from slackclient import SlackClient


class Handler(object):
    def __init__(self, CONF):
        self.slack_token = CONF["slack"]["token"]
        self.bot_id = str(CONF["slack"]["bot_id"])

        self.sc = None

    def setup(self):
        self.sc = SlackClient(self.slack_token)
        return self

    def run(self, result, conf):
        slack_channel = conf

        print(
            self.sc.api_call(
                "chat.postMessage",
                channel=slack_channel,
                username="hamb",
                as_user="true",
                text=result["summary"],
            )
        )