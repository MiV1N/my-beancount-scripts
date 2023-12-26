from shutil import copyfile

from beancount.query import query

from ..accounts import public_accounts


class Deduplicate:

    def __init__(self, entries, option_map):
        self.entries = entries
        self.option_map = option_map
        self.beans = {}

    def find_duplicate(self, entry, money, unique_no=None, replace_account='', currency='CNY'):
        
        if self.entries == None or entry == None:
            return False
        
        # 要查询的是实际付款的账户，而不是支出信息
        bql = "SELECT flag, filename, lineno, location, account, year, month, day, str(entry_meta('timestamp')) as timestamp, metas() as metas WHERE year = {} AND month = {} AND day = {} AND number(convert(units(position), '{}')) = {} ORDER BY timestamp ASC".format(
            entry.date.year, entry.date.month, entry.date.day, currency, money)
        items = query.run_query(self.entries, self.option_map, bql)
        length = len(items[1])
        if (length == 0):
            return False
        updated_items = []
        for item in items[1]:
            same_trade = False
            item_timestamp = item.timestamp.replace("'", '')
            # 如果已经被录入了，且unique_no相同，则判定为是同导入器导入的同交易，啥都不做
            if unique_no != None:
                if unique_no in entry.meta and unique_no in item.metas:
                    if item.metas[unique_no] == entry.meta[unique_no]:
                        same_trade = True

            if same_trade:
                return True
            # 否则，可能是不同账单的同交易，此时判断时间


            # 如果某个导入器的数据没有时间戳，则判断其为「还需进一步处理」的同笔交易
            # 例如，手工输入的交易，打上支付宝订单号。
            if (
                (not 'timestamp' in entry.meta) or
                # item_timestamp == entry.meta['timestamp'] or
                item.timestamp == 'None' or
                item.timestamp == ''
            ):
                print("有交易没有时间戳")
                # updated_items.append(item)
                # if replace_account != '' and item.account in public_accounts:
                #     self.update_transaction_account(
                #         item.location, item.account, replace_account)

                # 自定义meta不齐，这里补全信息
                # for key, value in entry.meta.items():
                #     if key == 'filename' or key == 'lineno':
                #         continue
                #     if not key in item.metas:
                #         item.metas[key] = value
                #     elif value != item.metas[key]:
                #         item.metas[key] += value
                        # self.append_text_to_transaction(
                        #     item.filename, item.lineno, '{}: "{}"'.format(key, value))
            
            # 如果有时间戳，且时间戳在误差范围，则判定为同交易
            # 100%确认是同一笔交易后，将当前的describe信息添加到之前的交易中
            time_gap = abs(int(item_timestamp) - int(entry.meta['timestamp'])) # 单位:秒
            tolerance = 10 #容差为10s
            if 'timestamp' in entry.meta and time_gap <= tolerance:
                
                for idx,transaction in enumerate(self.entries):
                    if item_timestamp == transaction.meta['timestamp']:
                        # 补全 meta 信息
                        for key, value in entry.meta.items():
                            if key == 'filename' or key == 'lineno':
                                continue
                            if not key in item.metas:
                                transaction.meta[key] = value
                            elif value != item.metas[key]: #主要是note
                                transaction.meta[key] += value

                        # posting补全
                        unknown_posts = [ post for post in transaction.postings if "Unknown" in post.account]
                        if len(unknown_posts) > 0:
                            all_posting = []
                            all_posting.extend(transaction.postings)
                            all_posting.extend(entry.postings)
                            new_postings = self.postings_merge(all_posting)
                            transaction.postings.clear() 
                            transaction.postings.extend(new_postings) 

                        # 补全描述信息 和 flag
                        flag = "*" if ("*" == transaction.flag) or ("*" == transaction.flag) else "!"
                        new_transaction = transaction._replace(narration=transaction.narration + entry.narration,flag=flag)
                        del self.entries[idx] #不会再往后迭代了，这里删除是安全的
                        self.entries.append(new_transaction)
                        same_trade = True
                        break    
                break
                
        # if len(updated_items) > 1:
        #     for item in updated_items:
        #         self.update_transaction_flag(item.location, item.flag, '!')
        return same_trade

    def postings_filte(self,postings:list):
        new_posting = postings[0] #合并为一个
        number = postings[0].units.number

        is_new_posting_ok = False
        if ("Unknown" not in new_posting.account) and \
            ("Transfer:Heyao" not in new_posting.account):
            is_new_posting_ok = True

        tmp_post = None
        for post in postings[1:]:

            # 前面的bql 条件为金额相同，这里不会存在金额不同的金额
            # if number != post.units.number:
            #     print("！！！同一个交易的金额不匹配")

            if 'Unknown' not in post.account:
                if "Transfer:Heyao"  in post.account:
                    tmp_post = post
                else:
                    if not is_new_posting_ok:
                        is_new_posting_ok = True
                        tmp_post = None
                        new_posting = post

                    else: #多个非Unknown的情况
                        if new_posting.units.number != post.units.number:
                            print("!!!相同交易的金额不同")
                        if new_posting.account != post.account:
                            print("!!!相同交易的账户不同")

        #  优先使用亲情付账户，其次是随便取一个
        if not is_new_posting_ok: 
            new_posting = tmp_post if tmp_post != None else new_posting

        return new_posting

    def postings_merge(self,postings:list):

        post_out = [post for post in postings if post.units.number < 0]
        post_in = [post for post in postings if post.units.number >= 0]

        new_post  = [self.postings_filte(post_out)]
        new_post.append(self.postings_filte(post_in))

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
