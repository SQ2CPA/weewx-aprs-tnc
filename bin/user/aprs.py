import datetime
import math
import time
import sys
import socket
from distutils.version import StrictVersion

import weewx
import weewx.units
import weeutil.weeutil
from weewx.engine import StdService

REQUIRED_WEEWX_VERSION = "3.0.0"
APRS_TNC_VERSION = "1.0.0"

if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_WEEWX_VERSION):
    raise weewx.UnsupportedFeature("WeeWX APRS TNC %s requires WeeWX %s or greater, got %s" % (APRS_TNC_VERSION, REQUIRED_WEEWX_VERSION, weewx.__version__))

try:
    import logging
    from weeutil.logger import log_traceback
    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

    def log_traceback_error(prefix=''):
        log_traceback(log.error, prefix=prefix)
except ImportError:
    import syslog
    from weeutil.weeutil import log_traceback

    def logmsg(level, msg):
        syslog.syslog(level, 'aprs: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

    def log_traceback_error(prefix=''):
        log_traceback(prefix=prefix, loglevel=syslog.LOG_ERR)

def convert(v, obs, group, from_unit_system, to_units):
    ut = weewx.units.getStandardUnitType(from_unit_system, obs)
    vt = weewx.units.ValueTuple(v, ut[0], group)
    return weewx.units.convert(vt, to_units).value


def nullproof(key, data):
    if key in data and data[key] is not None:
        return data[key]
    return 0

def encode_ax25(callsign, ssid) -> bytearray:
    _callsign: bytes = callsign.encode('utf-8')
    encoded_callsign = []

    encoded_ssid = (int(ssid) << 1) | 0x60

    while len(_callsign) < 6:
        _callsign += b' '

    for pos in _callsign:
        encoded_callsign.append(bytes([pos << 1]))

    encoded_callsign.append(bytes([encoded_ssid]))

    if callsign == "WIDE2" and len(encoded_callsign) > 0:
        last_byte = encoded_callsign[-1][0]
        encoded_callsign[-1] = bytes([last_byte + 1])

    return b''.join(encoded_callsign)

class WeewxAprsTnc(StdService):
    def __init__(self, engine, config_dict):
        super(WeewxAprsTnc, self).__init__(engine, config_dict)

        d = config_dict.get('WeewxAprsTnc', {})

        lat = d.get('lat')
        if lat is None:
            station_lat_abs = abs(engine.stn_info.latitude_f)
            (frac, degrees) = math.modf(station_lat_abs)
            _temp = frac * 60.0
            (frac_minutes, minutes) = math.modf(_temp)
            decimal_minutes = frac_minutes * 100.0
            hemi = 'N' if engine.stn_info.latitude_f >= 0.0 else 'S'
            lat = "%02d%02d.%02d%s" % (degrees, minutes, decimal_minutes, hemi)

        self.lat = lat
        lon = d.get('lon')
        if lon is None:
            station_lon_abs = abs(engine.stn_info.longitude_f)
            (frac, degrees) = math.modf(station_lon_abs)
            _temp = frac * 60.0
            (frac_minutes, minutes) = math.modf(_temp)
            decimal_minutes = frac_minutes * 100.0
            hemi = 'E' if engine.stn_info.longitude_f >= 0.0 else 'W'
            lon = "%03d%02d.%02d%s" % (degrees, minutes, decimal_minutes, hemi)
        
        self.lon = lon
        
        self.comment = d.get('comment', '')
        self.symbol = d.get('symbol', '/_')
        
        self.callsign = d.get('callsign', None)
        self.ssid = int(d.get('ssid', 13))
        self.destination = d.get('destination', 'APLOX1')
        self.path = d.get('path', 'WIDE1-1,WIDE2-1')
        self.tnc = d.get('tnc', '127.0.0.1:8001')
        self.interval = int(d.get('interval', 300))
        
        self.last_check_time = 0
        
        tnc_address, tnc_port = self.tnc.split(':')
        tnc_port = int(tnc_port)
        
        self.tnc_address = tnc_address
        self.tnc_port = tnc_port
        
        self.ds_aware = weeutil.weeutil.tobool(d.get('daylight_saving_aware', False))
        
        data_binding = d.get('data_binding', 'wx_binding')
        
        self.dbm = self.engine.db_binder.get_manager(data_binding)

        binding = d.get('binding', 'loop').lower()
        if binding == 'loop':
            self.bind(weewx.NEW_LOOP_PACKET, self.handle_new_loop)
            interval_str = 'loop packet'
        else:
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.handle_new_archive)
            interval_str = 'archive record'
        
        loginf("version %s" % APRS_TNC_VERSION)
        loginf("got callsign=%s-%d" % (self.callsign, self.ssid))
        loginf("got destination=%s" % self.destination)
        loginf("got path=%s" % self.path)
        loginf("got lat=%s lon=%s" % (self.lat, self.lon))
        loginf("got symbol=%s" % self.symbol)
        loginf("got comment=%s" % self.comment)
        
        loginf("APRS packet will be sent to TNC every %s" % (self.interval))

    def handle_new_loop(self, event):
        self.handle_data(event.packet)

    def handle_new_archive(self, event):
        self.handle_data(event.record)

    def handle_data(self, event_data):
        try:
            if self.callsign == "N0CALL":
                raise Exception("Please set your callsign")
            
            current_time = time.time()
            
            if current_time - self.last_check_time >= self.interval:
                self.last_check_time = current_time
                
                data = self.calculate(event_data)
                
                self.send_data_to_tnc(data)
        except Exception as e:
            log_traceback_error(prefix='aprs: **** ')

    def calculate(self, packet):
        pu = packet.get('usUnits')
        
        data = dict()
        
        data['dateTime'] = packet['dateTime']
        data['windDir'] = nullproof('windDir', packet)
        
        v = nullproof('windSpeed', packet)
        
        data['windSpeed'] = convert(v, 'windSpeed', 'group_speed', pu, 'mile_per_hour')
        v = nullproof('windGust', packet)
        
        data['windGust'] = convert(v, 'windGust', 'group_speed', pu, 'mile_per_hour')
        
        v = nullproof('outTemp', packet)
        data['outTemp'] = convert(v, 'outTemp', 'group_temperature', pu, 'degree_F')
        
        if self.ds_aware:
            _delta = datetime.timedelta(hours=1)
            
            start_td = datetime.datetime.fromtimestamp(data['dateTime']) - _delta
            
            start_ts = time.mktime(start_td.timetuple())
        else:
            start_ts = data['dateTime'] - 3600
        
        v = self.calc_rain_in_period(start_ts, data['dateTime'])
        v = 0 if v is None else v
        
        data['hourRain'] = convert(v, 'rain', 'group_rain', pu, 'inch')
        
        if 'rain24' in packet:
            v = nullproof('rain24', packet)
        else:
            if self.ds_aware:
                _delta = datetime.timedelta(days=1)
                start_td = datetime.datetime.fromtimestamp(data['dateTime']) - _delta
                start_ts = time.mktime(start_td.timetuple())
            else:
                start_ts = data['dateTime'] - 86400
            
            v = self.calc_rain_in_period(start_ts, data['dateTime'])
            v = 0 if v is None else v
        
        data['rain24'] = convert(v, 'rain', 'group_rain', pu, 'inch')
        
        if 'dayRain' in packet:
            v = nullproof('dayRain', packet)
        else:
            start_ts = weeutil.weeutil.startOfDay(data['dateTime'])
            v = self.calc_rain_in_period(start_ts, data['dateTime'])
            v = 0 if v is None else v
        
        data['dayRain'] = convert(v, 'rain', 'group_rain', pu, 'inch')
        
        data['outHumidity'] = nullproof('outHumidity', packet)
        
        v = nullproof('barometer', packet)
        
        data['barometer'] = convert(v, 'pressure', 'group_pressure', pu, 'mbar')
        
        return data

    def send_data_to_tnc(self, data):
        fields = list()
        
        fields.append("%s" % self.lat)
        fields.append("%s" % self.symbol[0])
        fields.append("%s" % self.lon)
        fields.append("%s" % self.symbol[1])
        fields.append("%03d" % int(data['windDir']))
        fields.append("/%03d" % int(data['windSpeed']))
        fields.append("g%03d" % int(data['windGust']))
        fields.append("t%03d" % int(data['outTemp']))
        fields.append("r%03d" % int(data['hourRain'] * 100))
        fields.append("p%03d" % int(data['rain24'] * 100))
        fields.append("P%03d" % int(data['dayRain'] * 100))
        
        if data['outHumidity'] < 0 or 100 <= data['outHumidity']:
            data['outHumidity'] = 0
            
        fields.append("h%02d" % int(data['outHumidity']))
        fields.append("b%05d" % int(data['barometer'] * 10))
        fields.append(" %s" % self.comment)
        
        packet = "%s%s" % (time.strftime("/%d%H%Mz", time.gmtime(data['dateTime'])), ''.join(fields))
        
        try:
            with open("/tmp/aprs.pkt", 'w') as f:
                f.write(packet)
                f.write("\n")
                
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            client.connect((self.tnc_address, self.tnc_port))

            client.send(b"\r\rXFLOW OFF\rFULLDUP OFF\rKISS ON\rRESTART\r")
            
            path = b""
            
            els = self.path.split(',')
            
            for el in els:
                wide, number = el.split('-')
                
                path = path + encode_ax25(wide, int(number))

            client.sendall(b"\xc0\x00" + encode_ax25(self.destination, 112) + encode_ax25(self.callsign, self.ssid) + path + b"\x03\xf0" + packet.encode('utf-8') + b"\xc0")

            client.close()
        except Exception as e:
            log_traceback_error(prefix='aprs: **** ')

    def calc_rain_in_period(self, start_ts, stop_ts):
        val = self.dbm.getSql("SELECT SUM(rain) FROM %s WHERE dateTime>? AND dateTime<=?" % self.dbm.table_name, (start_ts, stop_ts))
        
        if val is None:
            return None
        return val[0]
