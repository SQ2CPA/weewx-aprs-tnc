# APRS TNC extension for WeeWX

The _APRS TNC_ extension generates an APRS compliant weather packet that will be sent to your TNC KISS service.

## Pre-requisites

This extension requires WeeWX v3.0.0 or greater and when used with WeeWX v4.0.0 or later can be used under Python 2 or Python 3.

### Installation

1.  Download the latest _APRS TNC_ extension from the [releases page](https://github.com/SQ2CPA/weewx-aprs-tnc/releases)

        $ wget https://github.com/SQ2CPA/weewx-aprs-tnc/releases/download/v1.0.0/aprs-tnc-1.0.0.zip

2.  Install the _APRS TNC_ extension downloaded at step 1 using the `weectl` utility:

        $ weectl extension install aprs-tnc-1.0.0.zip

3.  Set your callsign, comment and more in `/etc/weewx/weewx.conf` file

4.  In `/etc/weewx/weewx.conf`, modify the [Engine] [[Services]] section by adding the WeewxAprsTnc service to the list of process services to be run:

        [Engine]
            [[Services]]

                process_services = .., user.aprs.WeewxAprsTnc

5.  Restart WeeWX:

        $ sudo /etc/init.d/weewx restart

    or

        $ sudo service weewx restart

    or

        $ sudo systemctl restart weewx
