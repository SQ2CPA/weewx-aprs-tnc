import weewx

from distutils.version import StrictVersion
from setup import ExtensionInstaller

REQUIRED_WEEWX_VERSION = "3.0.0"
APRS_TNC_VERSION = "1.0.0"

def loader():
    return AprsTncInstaller()

class AprsTncInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_WEEWX_VERSION):
            raise weewx.UnsupportedFeature("WeeWX APRS TNC %s requires WeeWX %s or greater, got %s" % (APRS_TNC_VERSION, REQUIRED_WEEWX_VERSION, weewx.__version__))
        
        super(AprsTncInstaller, self).__init__(
            version=APRS_TNC_VERSION,
            name='APRS TNCC',
            description='DESCRIPTION',
            author="SQ2CPA",
            author_email="sq2cpa<@>gmail.com",
            files=[('bin/user', ['bin/user/aprs.py'])],
            process_services='user.aprs.WeewxAprsTnc',
            config={
                'WeewxAprsTnc': {
                    'callsign': 'N0CALL',
                    'ssid': 13,
                    'destination': 'APLOX1',
                    'path': 'WIDE1-1,WIDE2-1',
                    'symbol': '/_',
                    'comment': 'My WeeWX station',
                    'tnc': '127.0.0.1:8001',
                    'interval': 300
                },
            }
        )
