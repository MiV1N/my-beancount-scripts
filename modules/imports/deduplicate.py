from shutil import copyfile

from beanquery import query
# from beancount.query import query

from ..accounts import public_accounts
from enum import  IntEnum

# 查询语句:bean-query main.bean "SELECT entry, entry.meta, meta FROM YEAR = 2023"
# 查询结果:
# 
# entry的结果
# Transaction(
#     meta={
#         'filename': 'C:\\D\\code\\beancount\\beancountfiles\\datas\\2023\\20240107.bean', 
#         'lineno': 18799, 
#         'trade_time': '2023-12-31 14:46:58', 
#         'timestamp': '1704005218', 
#         'shop_trade_no': '10000495012023123103563043744572', 
#         'wechat_trade_no': '100004950123123100024225927580939633', 
#         'note': '群收款,郑昊,/,/', 
#         '__tolerances__': {'CNY': Decimal('0.005')}
#     },
#     date=datetime.date(2023, 12, 31), 
#     flag='!', 
#     payee='郑昊', 
#     narration='群收款,郑昊,/,/', 
#     tags=frozenset(), 
#     links=frozenset(), 
#     postings=[
#         Posting(
#             account='Expenses:Unknown', 
#             units=123.00 CNY, 
#             cost=None, 
#             price=None, 
#             flag=None, 
#             meta={'filename': 'C:\\D\\code\\beancount\\beancountfiles\\datas\\2023\\20240107.bean', 'lineno': 18805}
#         ), 
#         Posting(
#           account='Assets:MobilePayment:WeChat', 
#           units=-123.00 CNY, 
#           cost=None, 
#           price=None, 
#           flag=None, 
#           meta={'filename': 'C:\\D\\code\\beancount\\beancountfiles\\datas\\2023\\20240107.bean', 'lineno': 18806})
#     ]
# ) 
# 
# entry.meta的结果
# {'trade_time': '2023-12-31 14:46:58', 'timestamp': '1704005218', 'shop_trade_no': '10000495012023123103563043744572', 'wechat_trade_no': '100004950123123100024225927580939633', 'note': '群收款,郑昊,/,/'} 
# 
# meta的结果:
#  {'filename': 'C:\\D\\code\\beancount\\beancountfiles\\datas\\2023\\20240107.bean', 'lineno': 18806}
# 
# 当执行查询 SELECT entry,entry.meta, meta FROM YEAR = 2023 时：
#     entry.meta 引用的是交易级别的元数据（即整个交易的元数据）
#     meta 引用的是过账级别的元数据（即当前过账行的元数据）
# 
# 这就是为什么两者的结果会不同。如果某个元数据只在交易级别定义，那么它只会出现在 entry.meta 中；如果某个元数据只在过账级别定义，那么它只会出现在 meta 中。
# 
# beancount/parser/printer.py
# 在META_IGNORE集合中,有意的被过滤，目的应该是只返回用户添加的元信息： printer.py:141
# META_IGNORE = {"filename", "lineno"}
# 
# 如果要返回这两个元信息可以使用
# SELECT ANY_META("filename"), ANY_META("lineno") FROM YEAR = 2023 时：

class Deduplicate:

    def __init__(self, entries, option_map):
        self.entries = entries
        self.option_map = option_map
        self.beans = {}

    def find_duplicate(self, entry, money, unique_no=None, replace_account='', currency='CNY'):
        return False
        if self.entries == None or len(self.entries) == 0 or entry == None:
            return False
        
        # 资产的支出或收入
        asset_amount = entry.postings[0].units.number if "Assets" in entry.postings[0].account else -entry.postings[0].units.number
        # 查询已经导入的日期相同金额相同的交易,account正则匹配A
        bql = f"""SELECT 
                    flag, 
                    str(entry_meta('timestamp')) as timestamp, 
                    entry.meta as metas, 
                    entry
                WHERE 
                    year = {entry.date.year} AND 
                    month = {entry.date.month} AND 
                    day = {entry.date.day} AND 
                    number(convert(units(position), '{currency}')) = {asset_amount} AND   
                    account ~ 'Assets'
                ORDER BY timestamp ASC"""

        items = query.run_query(self.entries, self.option_map, bql)
        rows = items[1]

        length = len(rows)
        if (length == 0):
            return False
        
        updated_items = []
        for row in rows:
            _flag, _timestamp, _metas, _entry = row
            _postings = _entry.postings
            # item_timestamp = _timestamp.replace("'", '')

            ######### unique_no 相同，一定是同一个文件导入了两次的相同交易 ###############
            # 直接丢弃新交易
            if unique_no != None and _metas != None:
                if unique_no in entry.meta and unique_no in _metas:
                    if _metas[unique_no] == entry.meta[unique_no]:
                        return True

            ########### 不同文件导入的交易，比如 支付宝的记录和银行卡的记录 ##############
            # 支付宝使用银行卡付款，导致同一条交易在不同的文件中各出现一次
            # 
            # 意图: 判断时间戳有无(自动导入的一定有时间戳)，判定是是否是手工记录与文件记录重复交易
            # 如果某个导入器的数据没有时间戳，则判断其为「手工输入的交易」，需要进行合并，比如打上支付宝订单号。
            

            # 如果已导入的条目和待导入的条目都有时间戳，但时间间隔>tolerance，认为是不同交易
            
            tolerance = 70 #容差为70s , 支付宝的账单时间只到分钟，所以这里的容差最小都要是60s
            if (
                ('timestamp' in entry.meta) and
                (_timestamp != 'None' or _timestamp != '') 
            ):
                time_gap = abs(int(_timestamp) - int(entry.meta['timestamp'])) # 单位:秒
                if time_gap > tolerance:
                    continue

            # 添加到待合并的列表
            updated_items.append(row)

        be_modify_row = None
        # 如果待合并的列表不为空，则进行合并
        if len(updated_items) == 0:
            return False
        elif len(updated_items) == 1:
            be_modify_row = updated_items[0]
        else:
            # 合并交易
            min_time_gap = 9999
            min_time_gap_index = 0
            for __index,__row in enumerate(updated_items):

                _flag, _timestamp, _metas, _entry = __row
                _postings = _entry.postings
                # 选择timestamp与entry.meta['timestamp']最接近的交易
                # 计算时间差
                time_gap = abs(int(_entry.meta['timestamp']) - int(entry.meta['timestamp']))
                if time_gap < min_time_gap:
                    min_time_gap = time_gap
                    min_time_gap_index = __index

            
            be_modify_row = updated_items[min_time_gap_index]


        _flag, _timestamp, _metas, _entry = be_modify_row
        _postings = _entry.postings
        ########### 剩下的需要合并的处理的条件 #######
        # 1. 待导入和已导入的交易中至少一方的meta中没有时间信息
        # 2. 待导入和已导入的交易meta中都存在时间信息，但是交易间隔时间差距在10s内

        ############META信息合并####################
        # 将待导入的交易信息补全到已经导入的交易的meta信息，当前待导入的数据丢掉
        for key, value in entry.meta.items():

            if key in ['filename','lineno',]:  
                continue

            ######## 已导入的条目中key不存在  #########
            # 待导入交易的新增属性，直接添加到已导入的交易中
            if _metas == None or key not in _metas: 
                _metas[key] = value
                continue

            ######### key存在但是为None，'' #########
            # 处理时间信息可能一方为空()，或者双方都为空 #
            # 可能性:
            # 1. _metas中为None 或 '', 待导入中value==''或者None  -> 被待导入的value替换
            # 2. _metas中为None 或 '', 待导入中value有值          -> 被待导入的value替换
            # 3. _metas中有值        , 待导入中value==''或者None  -> 保留_metas中的值，即:不处理该情况
            # 4. _metas中有值        , 待导入中value有值          -> 需要区分处理，是合并，还是保留其一
            if _metas[key] == None or _metas[key].strip() == '':  #情况1，2
                _metas[key] = value.strip()    
                continue  
            
            if value != None or value.strip()  != '':            # 情况4
                if key in ['trade_time','timestamp']:            # 时间信息保留精度高的一个
                    if key == "trade_time" and _metas['trade_time'][-2:] == "00":          #秒为0，形如:'2024-02-26 21:24:00'，用于处理支付宝这样时间只到分钟
                        _metas[key] = value          #  使用待导入的时间
                    if key == "timestamp" and int(_metas["timestamp"]) % 60 == 0:               #秒为0
                        _metas[key] = value          #  使用待导入的时间

                elif value != _metas[key]:                       #其他文本信息，直接合并，主要是note
                    _metas[key] += value

            ###########posting合并#############
            # 1. Unknown需要判断是否有未知账户
            # 2. "Transfer" 只是表示转账，加上"亲情卡"可以确定是情亲付，且是未处理的，已经和并过account会变更，但是narration还是有亲情付的字样。
            unknown_posts = [ post for post in _postings if ("Unknown" in post.account) or ("Transfer" in post.account and "亲情卡" in _entry.narration) ]
            if len(unknown_posts) > 0:
                all_posting = []
                all_posting.extend(_postings)
                all_posting.extend(entry.postings)

                new_postings = Deduplicate.postings_merge(all_posting)

                _postings.clear() 
                _postings.extend(new_postings) 

            ################## 补全描述信息 和 flag ##############
            flag = "*" if ("*" == entry.flag) or ("*" == _flag) else "!"


            ################# 创建新的交易 ####################
            new_transaction = _entry._replace(narration=_entry.narration + entry.narration, flag=flag, meta=_metas, postings=_postings)

            # 替换已导入的交易条目
            # 查找相同条目
            index = self.entries.index(_entry)
            self.entries[index] = new_transaction
            return True
    
        # 遍历完查询出来的结果都没有相同的交易
        return False

    """
    选择其中一个合适的交易返回，其他交易过滤掉。
    Args:
        postings (list): 交易记录列表。
    Returns:
        Posting: 选择的交易记录。
    """
    @staticmethod
    def postings_filte( postings: list):
        class Account_type(IntEnum):
            NONE = 1
            UNKNOWN = 2
            FAMILY_PAYMENT = 3
            OTHER = 4                     # 消费账户
            MOBILEPAYMENT = 5             # 资产
            BANK = 6                      # 资产
            

        new_posting = None
        new_posting_type = Account_type.NONE

        # number = postings[0].units.number
       
        # 不确定的交易主要是 Unknown 和 亲情付，亲情付账户当前标注为:Transfer:Heyao 
        # --> 需要尽可能去除
        # 对于付款账户
        # --> 尽可能选择银行账户
        # 其他都无所谓
        for post in postings:


            # 确认交易类型
            if "Unknown"  in post.account:
                post_type = Account_type.UNKNOWN
            elif "Transfer:Heyao"  in post.account:
                post_type = Account_type.FAMILY_PAYMENT
            elif "MobilePayment"  in post.account:
                post_type = Account_type.MOBILEPAYMENT
            elif "Bank"  in post.account:
                post_type = Account_type.BANK
            else:
                post_type = Account_type.OTHER

            # 替换待返回交易临时存储
            if post_type > new_posting_type :
                new_posting = post 
                new_posting_type = post_type
            
            # 多个非正常账户的相同金额，这种情况程序可能有异常，需要提示定位
            # 银行和移动支付可以相同，因为移动支付最终扣的银行的钱，当前已经兼容了
            if  ((new_posting != post)  and
                 (new_posting_type == post_type == Account_type.OTHER)):
                print(f"交易合并选择冲突:\n交易:{new_posting.account},金额:{new_posting.units.number},与\n交易:{post.account},金额:{post.units.number}")
            # 下面的代码屏蔽，主要是导入脚本还有写问题，要继续遍历检查数据是不是有问题
            # Account_type.NORMAL 类型可以不用继续遍历了
            # if new_posting_type == Account_type.NORMAL:
            #     return new_posting

        return new_posting

    @staticmethod
    def postings_merge(postings:list):

        post_out = [post for post in postings if post.units.number < 0]
        post_in = [post for post in postings if post.units.number >= 0]

        new_post  = [Deduplicate.postings_filte(post_out)]
        new_post.append(Deduplicate.postings_filte(post_in))

        return  new_post
        

    def read_bean(self, filename):
        if filename in self.beans:
            return self.beans[filename]
        with open(filename, 'r') as f:
            text = f.read()
            self.beans[filename] = text.split('\n')
        return self.beans[filename]

    def update_transaction_account(self, location, old_account, new_account):
        file_items = location.split(':')
        lineno = int(file_items[1])
        lines = self.read_bean(file_items[0])
        lines[lineno - 1] = lines[lineno - 1].replace(old_account, new_account)
        print("Updated account from {} to {} at {}".format(
            old_account, new_account, location))

    def append_text_to_transaction(self, filename, lineno, text):
        if filename[0] == '<':
            return
        lines = self.read_bean(filename)
        lines[lineno - 1] += '\n	' + text
        print("Appended meta {} to {}:{}".format(text, filename, lineno))

    def update_transaction_flag(self, location, old_flag, new_flag):
        if len(location) <= 0:
            return
        if location[0] == '<':
            return
        file_items = location.split(':')
        lineno = int(file_items[1])
        lines = self.read_bean(file_items[0])
        lines[lineno - 1] = lines[lineno - 1].replace(old_flag, new_flag, 1)
        print("Updated flag to {} at {}".format(new_flag, location))

    def apply_beans(self):
        for filename in self.beans:
            if filename[0] == '<':
                continue
            copyfile(filename, filename + '.bak')
            with open(filename, 'w') as f:
                f.write('\n'.join(self.beans[filename]))
