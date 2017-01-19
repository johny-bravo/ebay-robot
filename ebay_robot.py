#!/usr/bin/python
import sys
import time
import json
import smtplib
import collections
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ebaysdk.finding import Connection


def sv_log_msg(msg, log_file):
    with open(log_file, 'a') as lf:
        lf.write('%d\t%s\n' % (time.time(), msg))


def sv_log_err(err, log_file):
    err = str(err)
    line = str(sys.exc_info()[-1].tb_lineno)
    with open(log_file, 'a') as lf:
        lf.write('%d\tline %s\t%s\n' % (time.time(), line, err))


def wr_html(str_to_wrap):
    """ wrap string in basic html """
    return '<html><head></head><body>%s</body></html>' % str_to_wrap


def wr_tag(tag, str_to_wrap, options=''):
    """ wrap string in html <tag> """
    if options:
        options = ' %s' % options
    return '<%s%s>%s</%s>' % (tag, options, str_to_wrap, tag)


def wr_img(url, w, h):
    """ wrap img url in <img src> """
    return '<img src="%s" width="%s" height="%s"/>' % (url, w, h)


def wr_hrf(url, title):
    """ wrap url in <a href> """
    return '<a href="%s">%s</a>' % (url, title)


class EbayRobot(object):
    def __init__(self, id_dict, config):

        self.id_dict = id_dict

        self.crit_err = 0
        self.dict_needs_update = 0
        self.crnt_found_items = 0
        self.crnt_srch_key = ''
        self.crnt_srch_type = ''

        self.delay = config['delay']
        self.srch_conf_lst = config['srch']

        self.ids_file = config['ids']
        self.stats_file = config['stats']
        self.err_file = config['errlog']

        self.appid = config['rbt']['appid']
        self.ya_host = config['rbt']['ya_host']
        self.ya_port = config['rbt']['ya_port']
        self.ya_usr = config['rbt']['ya_usr']
        self.ya_pwd = config['rbt']['ya_pwd']
        self.from_email = config['rbt']['from_email']
        self.to_email = config['rbt']['to_email']

        self.api = Connection(appid=self.appid, config_file=None)

    def search_data(self, srch_config):

        """
        search api
        return {dict}
        """
        self.crnt_srch_key = srch_config['keywords'].title()
        self.crnt_srch_type = srch_config['type'][0]

        self.api.execute('findItemsAdvanced', {
            'keywords': srch_config['keywords'],
            'categoryId': '27386',
            'itemFilter': [
                {'name': 'Condition',
                 'value': ['1000', '1500', '2000', '2500', '3000']},
                {'name': 'LocatedIn', 'value': 'US'},
                {'name': 'ListedIn', 'value': 'EBAY-US'},
                {'name': 'MinPrice', 'value': srch_config['price_min'],
                 'paramName': 'Currency',
                 'paramValue': 'USD'},
                {'name': 'MaxPrice', 'value': srch_config['price_max'],
                 'paramName': 'Currency',
                 'paramValue': 'USD'},
                {'name': 'ListingType',
                 'value': srch_config['type']}
            ],
            'paginationInput': {
                'entriesPerPage': '25',
                'pageNumber': '1'
            },
            'sortOrder': 'StartTimeNewest'
        })
        return self.api.response.dict()

    def parse_response(self, response_dict):
        """
        parse api {response} and spit out html for email or ''
        """

        found_items_filtered = []
        if 'item' in response_dict['searchResult']:
            found_items = response_dict['searchResult']['item']
            for itm in found_items:
                if itm['itemId'] not in self.id_dict:
                    found_items_filtered.append(itm)
        else:
            self.dict_needs_update = 0
            return ''

        if len(found_items_filtered) <= 0:
            self.dict_needs_update = 0
            return ''

        self.dict_needs_update = 1

        tb_head = ''
        tb_clr = 'style="background-color:#E4EDF0;"'
        tb_names = ['img', 'title', 'best offer', 'price']

        for name in tb_names:
            tb_head += wr_tag('th', name)
        tb_head = wr_tag('tr', tb_head, options=tb_clr)

        tb_all_rows = ''
        cnt = 0
        for itm in found_items_filtered:
            itm_id = itm['itemId']
            tb_row = ''

            fltr_d = collections.OrderedDict()
            fltr_d['img'] = itm['galleryURL']
            fltr_d['url'] = itm['viewItemURL']
            if itm['listingInfo']['bestOfferEnabled'] == 'true':
                fltr_d['bo'] = 'yes'
            else:
                fltr_d['bo'] = 'no'
            fltr_d['price'] = itm['sellingStatus']['currentPrice']['value']

            self.id_dict[itm_id] = {
                'url': fltr_d['url'],
                'price': fltr_d['price']
            }

            for k, v in fltr_d.iteritems():
                if k == 'url':
                    v = wr_hrf(v, itm['title'])
                    tb_row += wr_tag('td', v)
                elif k == 'img':
                    v = wr_img(v, 50, 50)
                    tb_row += wr_tag('td', v)
                else:
                    tb_row += wr_tag('td', v)

            if cnt % 2 == 1:
                row_clr = tb_clr
            else:
                row_clr = ''

            tb_row = wr_tag('tr', tb_row, row_clr)
            tb_all_rows += tb_row
            cnt += 1

        tb_head += tb_all_rows
        tb_full = wr_tag(
            'table', tb_head, options='style="width:100%" cellpadding="10"')
        mail_body = wr_tag('body', tb_full)

        css_style = 'table,th,td{border:1px;}' \
                    'a, a:visited, .ii a[href] { color:#000001!important; ' \
                    'text-decoration:none;}' \
                    'a:hover, .ii a[href]:hover{ text-decoration:underline;}'

        css_style_full = wr_tag('style', css_style)
        mail_head = wr_tag('head', css_style_full)
        mail_html = wr_tag('html', mail_head + mail_body)

        self.crnt_found_items = len(found_items_filtered)
        return mail_html

    def send_mail(self, mail_html, subj=''):
        if not subj:
            subj = "Found %d new %s %s" % (self.crnt_found_items,
                                           self.crnt_srch_type,
                                           self.crnt_srch_key)
            self.crnt_found_items = 0

        msg = MIMEMultipart()
        msg['From'] = 'Ebay Robot <' + self.from_email + '>'
        msg['To'] = self.to_email
        msg['Subject'] = subj
        msg.attach(MIMEText(mail_html, 'html'))

        server = smtplib.SMTP_SSL(host=self.ya_host, port=self.ya_port)
        server.login(self.ya_usr, self.ya_pwd)

        text = msg.as_string()
        server.sendmail(self.from_email, self.to_email, text)
        server.quit()

    def save_dict(self):
        if self.dict_needs_update:
            with open(self.ids_file, 'r') as in_file:
                try:
                    data = json.load(in_file)
                    data.update(self.id_dict)
                except ValueError, e:
                    sv_log_err(e, self.err_file)
                    data = self.id_dict
            with open(self.ids_file, 'w') as out_file:
                out_file.write(json.dumps(data, indent=2))

    def stats_init(self):
        stats_data = {
            'req': 0,
            'found': 0,
            'err': 0,
            'tm_last': time.time(),
        }
        try:
            with open(self.stats_file, 'r') as stats_file:
                stats_data = json.load(stats_file)
        except IOError, e:
            sv_log_err(e, self.err_file)
            with open(self.stats_file, 'w'):
                pass
        except ValueError, e:
            sv_log_err(e, self.err_file)
            pass

        return stats_data

    def stats_update(self, stat_upd_dict):
        with open(self.stats_file, 'r') as infile:
            try:
                stats_data = json.load(infile)
            except ValueError, e:
                sv_log_err(e, self.err_file)
                stats_data = {}

        with open(self.stats_file, 'w') as outfile:
            stats_data.update(stat_upd_dict)
            outfile.write(json.dumps(stats_data, indent=2))

    def run(self):
        """
        email on found or error
        """
        srch_conf_lst = self.srch_conf_lst
        tm_day = 24 * 60 * 60
        upd_freq = 30 * 60  # save stats approx every 30 min

        while 1:
            stats = self.stats_init()
            for f in range(tm_day):
                if (f + 1) % upd_freq == 0:
                    self.stats_update(stats)
                try:
                    for srch_config in srch_conf_lst:
                        srch_data = self.search_data(srch_config)
                        stats['req'] += 1
                        # .parse_response() sets .crnt_found_items
                        resp_str = self.parse_response(srch_data)
                        if resp_str:
                            stats['found'] += self.crnt_found_items
                            # .send_mail() resets .crnt_found_items to 0
                            self.send_mail(resp_str)
                            self.save_dict()
                except Exception, e:
                    sv_log_err(e, self.err_file)
                    self.crit_err += 1
                    stats['err'] += 1
                    er_html = wr_html(str(e))
                    er_subj = 'An Error Occured'
                    self.send_mail(er_html, er_subj)
                    if self.crit_err >= 3:
                        sv_log_msg('Too much critical errors.'
                                   ' Gonna sleep for some time', self.err_file)
                        self.crit_err = 0
                        time.sleep(60 * 60)

                finally:
                    time.sleep(self.delay)

            tm_crnt = time.time()
            if (tm_crnt - stats['last']) >= tm_day:
                stat_str = 'Requests made: %d. ' \
                           'Items found: %d. ' \
                           'Critical errors occured: %d' % (
                               stats['req'], stats['found'], stats['err']
                           )
                stat_html = wr_html(stat_str)
                stat_subj = 'Stats report #%d' % tm_crnt

                stats_reset = {
                    'req': 0,
                    'found': 0,
                    'err': 0,
                    'tm_last': tm_crnt,
                }
                self.send_mail(stat_html, stat_subj)
                self.stats_update(stats_reset)


def setup():
    with open('config.json', 'r') as conf_file:
        config = json.load(conf_file)

    try:
        with open(config['ids'], 'r') as ids_file:
            ids_dict = json.load(ids_file)
    except IOError, e:
        sv_log_err(e, config['errlog'])
        with open(config['ids'], 'w'):
            ids_dict = {}
    except ValueError, e:
        sv_log_err(e, config['errlog'])
        ids_dict = {}
    return config, ids_dict


if __name__ == '__main__':
    cnf, ids = setup()
    ebr = EbayRobot(ids, cnf)
    ebr.run()
