from shutil import copyfile
from enum import IntEnum
from beanquery import query
from ..accounts import public_accounts

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
class AccountType(IntEnum):
    NONE = 1
    UNKNOWN = 2
    FAMILY_PAYMENT = 3
    OTHER = 4           # 消费账户
    MOBILEPAYMENT = 5   # 资产
    BANK = 6            # 资产

class Deduplicate:
    META_IGNORE = {"filename", "lineno"}

    def __init__(self, entries, option_map):
        self.entries = entries or []
        self.option_map = option_map
        self.beans = {}

    def skip_add_to_beancount(self, entry):
        """判断是否跳过添加到 beancount，当前仅判断是否包含银行资产账户。"""
        return any("Assets:Bank" in posting.account for posting in entry.postings)

    def find_duplicate(self, entry, money, unique_no=None, replace_account='', currency='CNY'):
        if not self.entries or entry is None:
            return False

        should_skip = self.skip_add_to_beancount(entry)
        asset_amount = (
            entry.postings[0].units.number
            if "Assets" in entry.postings[0].account
            else -entry.postings[0].units.number
        )

        # 查询已经导入的日期相同金额相同的交易,account正则匹配Assets
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
        

        _, rows = query.run_query(self.entries, self.option_map, bql)

        if not rows:
            return should_skip or False

        updated_items = []
        for row in rows:
            _flag, _timestamp, _metas, _entry = row

            # 1. 唯一编号完全相同，直接判定为重复
            if unique_no and _metas and unique_no in entry.meta and unique_no in _metas:
                if _metas[unique_no] == entry.meta[unique_no]:
                    return True

            ########### 不同文件导入的交易，比如 支付宝的记录和银行卡的记录 ##############
            # 支付宝使用银行卡付款，导致同一条交易在不同的文件中各出现一次
            # 
            # 意图: 判断时间戳有无(自动导入的一定有时间戳)，判定是是否是手工记录与文件记录重复交易
            # 如果某个导入器的数据没有时间戳，则判断其为「手工输入的交易」，需要进行合并，比如打上支付宝订单号。
            #
            # 如果已导入的条目和待导入的条目都有时间戳，但时间间隔>tolerance，认为是不同交易

            # 2. 时间戳容差判断
            tolerance = 70  # 秒, 支付宝的账单时间只到分钟，所以这里的容差最小都要是60s
            if 'timestamp' in entry.meta and _timestamp not in ('None', ''):
                try:
                    time_gap = abs(int(_timestamp) - int(entry.meta['timestamp'])) # 单位:秒
                    if time_gap > tolerance:
                        continue
                except Exception:
                    continue

            updated_items.append(row)

        if not updated_items:
            return should_skip or False

        be_modify_row = self._select_best_match(updated_items, entry)
        if be_modify_row is None:
            return should_skip or False

        _flag, _timestamp, _metas, _entry = be_modify_row
        _postings = _entry.postings

        # 合并 meta 信息
        self._merge_meta(_metas, entry.meta)

        # 合并 postings
        if self._need_postings_merge(_postings, _entry.narration):
            merged_postings = self.postings_merge(list(_postings) + list(entry.postings))
            _postings.clear()
            _postings.extend(merged_postings)

        # 合并 flag 和 narration
        new_flag = "*" if "*" in (entry.flag, _flag) else "!"
        new_narration = _entry.narration + entry.narration

        # 创建新的交易对象
        new_transaction = _entry._replace(
            narration=new_narration,
            flag=new_flag,
            meta=_metas,
            postings=_postings
        )

        # 替换原有条目
        try:
            index = self.entries.index(_entry)
            self.entries[index] = new_transaction
        except ValueError:
            pass  # 原条目未找到，忽略

        return True

    def _select_best_match(self, updated_items, entry):
        """从候选项中选择与 entry 最接近的项（按 timestamp）"""
        if len(updated_items) == 1:
            return updated_items[0]
        min_time_gap = float('inf')
        best_row = None
        for row in updated_items:
            _flag, _timestamp, _metas, _entry = row
            try:
                gap = abs(int(_entry.meta.get('timestamp', 0)) - int(entry.meta.get('timestamp', 0)))
            except Exception:
                gap = float('inf')
            if gap < min_time_gap:
                min_time_gap = gap
                best_row = row
        return best_row

    def _merge_meta(self, target_meta, source_meta):
        """合并 meta 信息，优先保留精度高的时间信息，合并 note 等文本。"""
        if target_meta is None:
            return
        for key, value in source_meta.items():
            if key in self.META_IGNORE:
                continue
            if target_meta is None or key not in target_meta:
                target_meta[key] = value
                continue
            if target_meta[key] is None or str(target_meta[key]).strip() == '':
                target_meta[key] = str(value).strip()
                continue
            if value is not None and str(value).strip() != '':
                # 时间信息优先保留精度高的
                if key in ('trade_time', 'timestamp'):
                    if key == "trade_time" and target_meta.get('trade_time', '')[-2:] == "00":
                        target_meta[key] = value
                    elif key == "timestamp" and int(target_meta.get("timestamp", 0)) % 60 == 0:
                        target_meta[key] = value
                elif value != target_meta[key]:
                    target_meta[key] += str(value)

    def _need_postings_merge(self, postings, narration):
        """判断是否需要合并 postings（存在 Unknown 或亲情卡）"""
        return any(
            ("Unknown" in post.account) or
            ("Transfer" in post.account and "亲情卡" in narration)
            for post in postings
        )

    @staticmethod
    def postings_filte(postings):
        """从一组 postings 中选择最合适的一个（优先级：银行 > 移动支付 > 其他 > 亲情付 > Unknown）"""
        best_posting = None
        best_type = AccountType.NONE
        for post in postings:
            post_type = Deduplicate._get_account_type(post.account)
            if post_type > best_type:
                best_posting = post
                best_type = post_type
            # 冲突提示
            if (
                best_posting != post and
                best_type == post_type == AccountType.OTHER
            ):
                print(
                    f"交易合并选择冲突:\n交易:{best_posting.account},金额:{best_posting.units.number},与\n"
                    f"交易:{post.account},金额:{post.units.number}"
                )
        return best_posting

    @staticmethod
    def _get_account_type(account):
        if "Unknown" in account:
            return AccountType.UNKNOWN
        elif "Transfer:Heyao" in account:
            return AccountType.FAMILY_PAYMENT
        elif "MobilePayment" in account:
            return AccountType.MOBILEPAYMENT
        elif "Bank" in account:
            return AccountType.BANK
        else:
            return AccountType.OTHER

    @staticmethod
    def postings_merge(postings):
        """合并 postings，分别处理正负金额，选出最优的入账和出账 posting。"""
        post_out = [post for post in postings if post.units.number < 0]
        post_in = [post for post in postings if post.units.number >= 0]
        merged = []
        if post_out:
            merged_post = Deduplicate.postings_filte(post_out)
            if merged_post:
                merged.append(merged_post)
        if post_in:
            merged_post = Deduplicate.postings_filte(post_in)
            if merged_post:
                merged.append(merged_post)
        return merged

    def read_bean(self, filename):
        """读取 bean 文件内容并缓存。"""
        if filename in self.beans:
            return self.beans[filename]
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().split('\n')
            self.beans[filename] = lines
        return self.beans[filename]

    def update_transaction_account(self, location, old_account, new_account):
        """更新指定位置的账户名。"""
        file_items = location.split(':')
        filename, lineno = file_items[0], int(file_items[1])
        lines = self.read_bean(filename)
        lines[lineno - 1] = lines[lineno - 1].replace(old_account, new_account)
        print(f"Updated account from {old_account} to {new_account} at {location}")

    def append_text_to_transaction(self, filename, lineno, text):
        """在指定行追加 meta 信息。"""
        if filename.startswith('<'):
            return
        lines = self.read_bean(filename)
        lines[lineno - 1] += '\n\t' + text
        print(f"Appended meta {text} to {filename}:{lineno}")

    def update_transaction_flag(self, location, old_flag, new_flag):
        """更新指定位置的 flag。"""
        if not location or location.startswith('<'):
            return
        file_items = location.split(':')
        filename, lineno = file_items[0], int(file_items[1])
        lines = self.read_bean(filename)
        lines[lineno - 1] = lines[lineno - 1].replace(old_flag, new_flag, 1)
        print(f"Updated flag to {new_flag} at {location}")

    def apply_beans(self):
        """将缓存的 bean 文件内容写回文件，并备份原文件。"""
        for filename, lines in self.beans.items():
            if filename.startswith('<'):
                continue
            copyfile(filename, filename + '.bak')
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
