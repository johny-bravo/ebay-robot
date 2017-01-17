import re
import json
import smtplib
import collections
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ebaysdk.finding import Connection


def wr_html(str_to_wrap):
    return '<html><head></head><body>%s</body></html>' % str_to_wrap


def wr_tag(tag, str_to_wrap, options=''):
    """ wrap in html, optional inline style """
    if options:
        options = ' %s' % options
    return '<%s%s>%s</%s>' % (tag, options, str_to_wrap, tag)


def wr_img(url, w, h):
    """ wrap in html """
    return '<img src="%s" width="%s" height="%s"/>' % (url, w, h)


def wr_hrf(url, title):
    """ wrap in html """
    return '<a href="%s">%s</a>' % (url, title)


class EbayRobot(object):
    def __init__(self, id_dict, config):

        self.id_dict = id_dict
        self.dict_needs_update = 0
        self.crnt_srch = ''

        self.srch_conf = config['srch']
        self.ids_file = config['ids']
        self.appid = config['rbt']['appid']
        self.ya_host = config['rbt']['ya_host']
        self.ya_port = config['rbt']['ya_port']
        self.ya_usr = config['rbt']['ya_usr']
        self.ya_pwd = config['rbt']['ya_pwd']
        self.from_email = config['rbt']['from_email']
        self.to_email = config['rbt']['to_email']

        self.api = Connection(appid=self.appid, config_file=None)

    def search_data(self, srch_config):

        self.crnt_srch = srch_config['keywords'].title()
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
                 'value': ['AuctionWithBIN', 'FixedPrice']}
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
        parse response dict and spit out html for email or ''
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
            self.id_dict[itm_id] = ''
            tb_row = ''

            filtered_d = collections.OrderedDict()
            filtered_d['g'] = itm['galleryURL']
            filtered_d['v'] = itm['viewItemURL']
            if itm['listingInfo']['bestOfferEnabled'] == 'true':
                filtered_d['l'] = 'yes'
            else:
                filtered_d['l'] = 'no'
            filtered_d['s'] = itm['sellingStatus']['currentPrice']['value']

            for k, v in filtered_d.iteritems():
                if k == 'v':
                    v = wr_hrf(v, itm['title'])
                    tb_row += wr_tag('td', v)
                elif k == 'g':
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

        return mail_html

    def send_mail(self, mail_html, subj=''):

        ths = len(re.findall(r'<th>', mail_html))
        tds = len(re.findall(r'<td>', mail_html))

        if ths > 0 and tds > 0:
            nm_fnd_itms = tds / ths
        else:
            nm_fnd_itms = 0

        if not subj:
            subj = "Found %d new %s" % (nm_fnd_itms, self.crnt_srch)

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
        if self.dict_needs_update == 1:
            with open(self.ids_file, 'r') as in_file:
                try:
                    data = json.load(in_file)
                    data.update(self.id_dict)
                except ValueError:
                    data = self.id_dict
            with open(self.ids_file, 'w') as out_file:
                out_file.write(json.dumps(data, sort_keys=True, indent=2))

    def run(self):
        srch_conf_lst = self.srch_conf
        try:
            for srch_config in srch_conf_lst:
                srch_data = self.search_data(srch_config)
                resp_str = self.parse_response(srch_data)
                if resp_str:
                    self.send_mail(resp_str)
                    self.save_dict()
        except Exception as e:
            er_html = wr_html(str(e))
            er_subj = 'An Error Occured'
            self.send_mail(er_html, er_subj)


if __name__ == '__main__':
    with open('config.json', 'r') as conf_file:
        cnf = json.load(conf_file)
    try:
        with open(cnf['ids'], 'r') as ids_file:
            ids = json.load(ids_file)
    except IOError:
        with open(cnf['ids'], 'w') as ids_file:
            ids = {}
    except ValueError:
        ids = {}

    #
    ebr = EbayRobot(ids, cnf)
    ebr.run()
