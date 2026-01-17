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
from tqdm import tqdm

Account支付宝 = 'Assets:MobilePayment:Alipay'

account_map = {
    "招商":"Assets:Bank:CMB:3007",
    "中信银行储蓄卡\(5999\)":"Assets:Bank:CITIC:5999",
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

        if not re.search(r'(alipay_record_|支付宝交易明细).*\.csv$', filename.name):
            raise Exception("not alipay ,skip")

        content = byte_content.decode('gbk')
        lines = content.split("\n")

        # 去除注释行，无效行
        start_lines = 0
        end_lines = 0
        for idx,line in enumerate(lines):
            if line.startswith("交易时间"):
                start_lines = idx
            
            if  line != '':
                end_lines = idx

        # print('Import Alipay: ' + lines[3])
        content = "\n".join(lines[start_lines:end_lines+1])

        self.content = content
        self.filename = filename.name
        self.line_num = end_lines - start_lines  #不再加1是为了排除标题行

        # 去重复
        self.deduplicate = Deduplicate(entries, option_map)

    def is_income(self,row):
        #优先'收/支'字段判定
        if (row['收/支']!= '') and (row['收/支'] in ('收入') ):
            return True
        elif (row['收/支']!= '') and (row['收/支'] in ('支出')):
            return False

        # 描述字段判定 row['收/支'] in ('不计收支') 
        income_describes = ["退款","赔付","转入","收益发放"]
        for _ in income_describes:
            if _ in row['商品说明']:
                return True
            
        # 描述字段判定支出 row['收/支'] in ('不计收支') 
        outcome_describes = [""]
        for _ in outcome_describes:
            if _ in row['商品说明']:
                return False

        print("！！！非收入/支出！！！！")
        print(f"{row['交易分类']},{row['交易对方']},{row['商品说明']},{row['备注']}")
        return False

    def parse(self):
        content = self.content
        f = StringIO(content)
        reader = DictReaderStrip(f, delimiter=',')
        transactions = []
        

        #进度展示
        with tqdm(total=self.line_num) as pbar:
            pbar.set_description(f'{self.filename}')

            # 解析账单
            # 不计收支类型 需要计入账单，因为不计收支主要是退款，但是付款被记录了，特别是上一个导入周期付款，下一个导入周期退款，导致处理为不计账单很难。
            for row in reader:
                if (row['交易状态'] != '') and (row['交易状态'] in ('交易关闭','冻结成功')):
                    pbar.update(1)
                    continue
    
                # 跳过 不计收支 并且 是退款成功的交易
                # 交易时间	交易分类	交易对方	对方账号	商品说明	收/支	金额	收/付款方式	交易状态	交易订单号	商家订单号	备注
                # 2025/7/18 23:40	充值缴费	浙江天猫技术有限公司	she***@service.aliyun.com	淘宝省钱卡	不计收支	9.9		交易关闭	"2025071822001310301401773053	"	"T3901P4639035205911913834	"	
                # 2025/7/18 14:16	退款	x***8	135******20	退款-【自动发货】汽水音乐VIP会员月卡  汽水音乐官方直冲秒到	不计收支	0.1	余额宝	退款成功	"2025071822001110301401375979_4638152664111913834	"	"T200P4638152664111913834	"	
                # 2025/7/18 14:10	日用百货	x***8	135******20	【自动发货】汽水音乐VIP会员月卡  汽水音乐官方直冲秒到	支出	0.1	余额宝	交易关闭	"2025071822001110301401375979	"	"T200P4638152664111913834	"	
                if (row['收/支'] != '') and (row['收/支'] in ('不计收支')) and ("退款成功" in row['交易状态']):
                    pbar.update(1)
                    continue

                # 跳过指定的收/付款方式（只要包含任一关键字就跳过）
                skip_keywords = ['工商银行储蓄卡(6614)']
                if (row['收/付款方式'] != '') and any(keyword in row['收/付款方式'] for keyword in skip_keywords):
                    pbar.update(1)
                    continue


                if (row['商品说明'] != '') and (row['商品说明'] in ('余额宝-自动转入','转账收款到余额宝')):  #余额宝也认为是余额，余额和余额宝的互转不记录
                    pbar.update(1)
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


                real_account = get_account_by_map(row['收/付款方式'])

                #收入
                if self.is_income(row) :
                    income = get_income_account_by_guess(row['交易对方'], description, time)
                    if income == 'Income:Unknown':
                        entry = entry._replace(flag='!')

                    price = row['金额']
                    # 金额为正，写入到支付宝的账户中
                    data.create_simple_posting(entry, real_account, price,'CNY')
                    data.create_simple_posting(entry, income, f"-{price}", 'CNY')
                    
                else:
                    out_account = get_account_by_guess(row['交易对方'], description, time)
                    if out_account == "Expenses:Unknown":
                        entry = entry._replace(flag='!')

                    price = row['金额']

                    # 金额为正，写入到支出的账户中
                    data.create_simple_posting(entry, out_account, price, 'CNY')
                    data.create_simple_posting(entry, real_account, f"-{price}",'CNY')


                
                # 合并相同时间戳的账单(支付宝的时间只精确到分钟，不能这样合并)
                # 支付宝在盒马上存在同一时间戳产生三个账单，但是银行卡只有一条合并的记录,合并后才能去重
                # 由于账单是时间排序的，相同的账单一定紧邻
                # if len(transactions) != 0 and transactions[-1].meta["timestamp"] == entry.meta['timestamp']:
                #     pre_entry = transactions[-1]

                #     amount_in = 0
                #     amount_in_post = None
                #     amount_out = 0
                #     amount_out_post = None

                #     for post in pre_entry.postings:
                #         amount = post.units.number
                #         if amount > 0:
                #             amount_in += amount
                #             amount_in_post = post
                #         elif amount < 0:
                #             amount_out += amount
                #             amount_out_post = post
                #         else: #使用医保挂号，出现支付金额为0
                #             amount_in_post = post if amount_in_post == None else amount_in_post
                #             amount_out_post = post if amount_in_post != None else amount_out_post

        
                #     new_units = amount_in_post.units._replace(number = amount_in)
                #     amount_in_post = amount_in_post._replace(units = new_units)

                #     new_units = amount_in_post.units._replace(number = amount_out)
                #     amount_out_post = amount_out_post._replace(units = new_units)

                #     pre_entry.postings.clear()
                #     pre_entry.postings.append(amount_in_post) 
                #     pre_entry.postings.append(amount_out_post) 
                # else:

                #去重
                amount = float(row['金额'])
                if not self.deduplicate.find_duplicate(entry, amount, 'alipay_trade_no'):
                    transactions.append(entry)

                pbar.update(1)

        # self.deduplicate.apply_beans()
        return transactions
