import argparse
import re
from datetime import datetime

from pathlib import Path
from beancount import loader
from beancount.core import data
from beancount.core.data import Amount
from beancount.parser import parser, printer


from modules.imports.alipay import Alipay
from modules.imports.cmb import CMB
# from modules.imports.abc_credit import ABCCredit
# from modules.imports.ccb_credit import CCBCredit
# from modules.imports.citic_credit import CITICCredit
from modules.imports.citic import CITICC
# from modules.imports.cmb_credit import CMBCredit
# from modules.imports.cmbc_credit import CMBCCredit
# from modules.imports.icbc_credit import ICBCCredit
# from modules.imports.icbc_debit import ICBCDebit
from modules.imports.wechat import WeChat
import logging
from modules.imports.deduplicate import  Deduplicate

# logging.basicConfig(level=logging.ERROR)
logging.basicConfig(level=logging.DEBUG)

# from modules.imports.yuebao import YuEBao
# from modules.imports.alipay_prove import AlipayProve

parser = argparse.ArgumentParser("import")
parser.add_argument("--path", help="CSV Path")
parser.add_argument("--entry", help="Entry bean path (default = main.bean)", default='')
parser.add_argument("--out", help="Output bean path", default='')
args = parser.parse_args()

entry = None
if args.entry != '':
    entry, errors, option_map = loader.load_file(args.entry)  #手动记录部分

# importers = [Alipay, AlipayProve, YuEBao, WeChat,
#              ABCCredit, CCBCredit, CITICCredit, CMBCCredit, CMBCredit, ICBCCredit,
#              ICBCDebit]
# importers = [Alipay,CMB,WeChat,CITICC]
importers = [CMB,CITICC]


all_path = Path(args.path)
files = list(all_path.rglob("*.csv"))
files.extend(list(all_path.rglob("*.xls")))

# 将包含“中信”或“CMB”名称的文件放到列表最前面
def file_priority(file):
    name = file.name.lower()
    if "中信" in name or "citic" in name or "cmb" in name:
        return 0
    return 1

files = sorted(files, key=file_priority)


new_entries = entry if entry != None and len(entry)>0 else []

# 文件解析
for file in files:
    logging.debug(f"处理文件：{file.name}")
    instance = None
    for importer in importers:
        try:
            with open(file, 'rb') as f:
                file_bytes = f.read()
                instance = importer(file, file_bytes, new_entries, option_map)
            
            _entries = instance.parse()
            new_entries.extend(_entries)

            break
        except Exception as e:
            logging.debug(e)
            pass



########写入文件###########
# 1. 先按date排序，之后按meta里面的timestamp排序
# 2. 由于银行卡是降序，这里也保持降序排列，方便核对
def sort_key(entry):  
    meta = getattr(entry, 'meta', '')  
    return (entry.date, meta["timestamp"])  
sorted_entries = sorted(new_entries, key=sort_key, reverse=True)


# 处理移动支付在调用银行接口的时候做的交易合并
# 例子：支付宝在1分钟内发生了两笔交易12.0和13.0，且收款方是同一家，在银行会合并成一条25.0的交易。
# 条件:(账单中看不出来)
# 1. 时间小于阈值，暂定1.5分钟
# 2. 付款方或收款方相同
# 支付宝:
# 交易时间	交易分类	交易对方	对方账号	商品说明	收/支	金额	收/付款方式	交易状态	交易订单号
# 2023/10/12 23:38	亲友代付	喜剧xx何(何x)	/	亲情卡	支出	34	招商银行储蓄卡(4436)	交易成功	"2023101204200190001082616792	"	"2023101222001194901408599790	"	
# 2023/10/12 23:38	亲友代付	喜剧xx何(何x)	/	亲情卡	支出	20.7	招商银行储蓄卡(4436)	交易成功	"2023101204200190001082616793	"	"2023101222001194901408288563	"	
# CMB:
# 交易日期	 交易时间	收入	支出	余额	交易类型	交易备注
# "20231012"	"23:38:53"		54.7	186278.99	"	银联快捷支付"	"	支付宝-支付宝-消费-博库网络有限公司"
# 合并检测条件
# 1. 在1.5分钟有>=3笔交易
# 2. 有一笔是银行卡交易
# 2. 其中多笔非银行交易相加可以等于银行卡交易

# time_gap = 90                           # 最大时间间隔

# merged_entries = []                   #存储合并处理之后的entry
# scan_index = 0                        #扫描窗口开始位置在sorted_entries中的index

# to_merge_entries = []                    #待合并处理的交易,也是扫描窗口中的数据
# for index,entry in enumerate(sorted_entries):
    
#     if scan_index > index:
#         continue
#     else:
#         scan_index = index

#     if to_merge_entries == []:
#         to_merge_entries.append(entry)

#     start_entry_timestamp = to_merge_entries[0].meta["timestamp"]

#     added_index = 0
#     for window_index,scan_entry in enumerate(sorted_entries[scan_index+1:]):
#         scan_entry_timestamp = scan_entry.meta["timestamp"]
#         added_index =  window_index + 1
#         # 超过时间间隔，扫描窗口前移
#         if int(start_entry_timestamp) - int(scan_entry_timestamp) > time_gap:
#             break
#         else:
#             to_merge_entries.append(scan_entry)
    
#     # 检查是否可以合并
#     merged_entrie = None                   #合并后的结果，正常情况应该只有一个
#     is_merged = False

#     if len(to_merge_entries) >2 :
        
#         # 合并
#         for sum_index, sum_entry in enumerate(to_merge_entries):

#             # 金额为正
#             amount = sum_entry.postings[0].units.number
#             amount = amount if amount >= 0 else (0-amount) 
#             for _index2, _entry2 in enumerate(to_merge_entries):

#                 if _index2 == sum_index:
#                     continue
                
#                 _amount = _entry2.postings[0].units.number  
#                 _amount = _amount if _amount >= 0 else (0-_amount) 
#                 amount -= _amount
            
#             merged_narration = ''
#             if amount == 0:
#                 logging.debug(f"有待合并的数据:{len(to_merge_entries)}条:")
#                 merged_entry = sum_entry
#                 all_postings = []
#                 for _index2, _entry2 in enumerate(to_merge_entries):
#                     if _index2 == sum_index:
#                         logging.debug(f'''合并->汇总：{_entry2.meta["trade_time"]},   {_entry2.postings[0].account}:{_entry2.postings[0].units},   {_entry2.postings[1].account}:{_entry2.postings[1].units},   {_entry2.narration}''')
#                     else:
#                         merged_narration += _entry2.narration
#                         logging.debug(f'''合并->其他：{_entry2.meta["trade_time"]},   {_entry2.postings[0].account}:{_entry2.postings[0].units},   {_entry2.postings[1].account}:{_entry2.postings[1].units},   {_entry2.narration}''')
#                         # 处理 账户 和 描述，以及时间
#                     all_postings.extend(_entry2.postings)

#                 new_postings = Deduplicate.postings_merge(all_postings)  #合并后金额可能是错误的
#                 #修改金额
#                 replaced_postings = []
#                 sum_entry_number = sum_entry.postings[0].units.number
#                 positive_number = sum_entry_number if sum_entry_number > 0 else (0-sum_entry_number)
#                 negative_number =  0 - positive_number

#                 for _posting in new_postings:
#                     _posting_number = _posting.units.number
#                     new_posting = _posting._replace(units=_posting.units._replace(number=positive_number if _posting_number > 0 else negative_number))
#                     replaced_postings.append(new_posting)
#                 merged_entrie = sum_entry._replace(narration=sum_entry.narration + merged_narration,  postings=replaced_postings)
#                 is_merged = True
#                 break

    
#     # 打印20231012日的交易
#     # if entry.date.strftime("%Y%m%d") == "20231012":
#     #     logging.info(f"20231012日的交易: {entry.meta['trade_time']}, 金额: {entry.postings[0].units}, 类型: {entry.postings[0].account}, 备注: {entry.narration}")

#     to_merge_entries = []
#     if merged_entrie != None:
#         merged_entries.append(merged_entrie)
#     else:
#         merged_entries.append(entry)
#         added_index = 1

#     scan_index += added_index

#     # 写入最终结果
merged_entries = sorted_entries
# 保存名称按交易时间区间命名
save_name = args.out
if save_name == "":
    start_date = merged_entries[-1].date.strftime("%Y%m%d")
    end_date = merged_entries[0].date.strftime("%Y%m%d")
    save_name = f'{all_path.absolute()}/{start_date}-{end_date}.bean'

with open(save_name, 'w', encoding='utf-8') as f:
    printer.print_entries(merged_entries, file=f)

print('Outputed to ' + save_name)
exit(0)

file = parser.parse_one('''
2018-01-15 * "测试" "测试"
	Assets:Test 300 CNY
	Income:Test

''')
print(file.postings)


file.postings[0] = file.postings[0]._replace(
    units=file.postings[0].units._replace(number=100))
print(file.postings[0])

data = printer.format_entry(file)
print(data)
