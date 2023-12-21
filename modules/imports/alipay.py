import calendar
import csv
import re
from zipfile import ZipFile
from datetime import date
from io import StringIO, BytesIO

import dateparser
from beancount.core import data
from beancount.core.data import Note, Transaction

from . import (DictReaderStrip, get_account_by_guess,
               get_income_account_by_guess)
from .base import Base
from .deduplicate import Deduplicate

Account支付宝 = 'Assets:Alipay'

account_map = {
    "招商":"Assets:Bank:CMB:3007"
}

account_map_res = dict([(key, re.compile(key)) for key in account_map])


def get_account_by_map(description):
    if description != '':
        for key, value in account_map.items():
            if account_map_res[key].findall(description):
                return value
    
    return Account支付宝

class Alipay(Base):

    def __init__(self, filename, byte_content, entries, option_map):

        if not re.search(r'alipay_record_.*\.csv$', filename.name):
            raise Exception("not alipay ,skip")

        content = byte_content.decode('gbk')
        lines = content.split("\n")

        # 去除注释行，无效行
        start_lines = 0
        for line in lines:
            if line.startswith("交易时间"):
                break
            start_lines += 1

        print('Import Alipay: ' + lines[3])
        content = "\n".join(lines[start_lines:])
        self.content = content

        # 去重复
        self.deduplicate = Deduplicate(entries, option_map)

    def parse(self):
        content = self.content
        f = StringIO(content)
        reader = DictReaderStrip(f, delimiter=',')
        transactions = []
        
        for row in reader:
            if (row['交易状态'] in ('交易关闭','冻结成功')) or \
               (row['收/支'] in ('不计收支') ) :
                continue
 
            # 准备元数据
            time = row['交易时间']
            # print("Importing {} at {}".format(row['商品说明'], time))
            
            meta = {}
            time = dateparser.parse(time)
            meta['alipay_trade_no'] = row['交易订单号']
            meta['trade_time'] = str(time)
            meta['timestamp'] = str(time.timestamp()).replace('.0', '')

            if row['商家订单号'] != '':
                meta['shop_trade_no'] = row['商家订单号']

            description = f"{row['交易分类']},{row['交易对方']},{row['商品说明']},{row['备注']}"
            meta['note'] = description

            meta = data.new_metadata(
                'beancount/core/testing.beancount',
                12345,
                meta
            )

            
            # 构造交易
            entry = Transaction(
                    meta,
                    date(time.year, time.month, time.day),
                    "*",
                    row['交易对方'],
                    description,
                    data.EMPTY_SET,
                    data.EMPTY_SET, []
                )


            account2 = get_account_by_map(row['收/付款方式'])

            #支出
            if row['收/支'] in ('支出'):
                account = get_account_by_guess(row['交易对方'], description, time)
                if account == "Expenses:Unknown":
                    entry = entry._replace(flag='!')

                price = row['金额']

                # 金额为正，写入到支出的账户中
                data.create_simple_posting(entry, account, price, 'CNY')
                data.create_simple_posting(entry, account2, f"-{price}",'CNY')

            #收入
            elif row['收/支'] in ('收入'):
                income = get_income_account_by_guess(row['交易对方'], description, time)
                if income == 'Income:Unknown':
                    entry = entry._replace(flag='!')

                price = row['金额']
                # 金额为正，写入到支付宝的账户中
                data.create_simple_posting(entry, account2, price,'CNY')
                data.create_simple_posting(entry, income, f"-{price}", 'CNY')

            else:
                print("非收入/支出")
                pass

            #去重
            amount = float(row['金额'])
            if not self.deduplicate.find_duplicate(entry, amount, 'alipay_trade_no'):
                transactions.append(entry)

        # self.deduplicate.apply_beans()
        return transactions
