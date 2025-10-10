use std::borrow::Cow;

use crate::common;
use crate::files::{BillProcessRules, CsvReader};
use beancount_core::{self as bc, account};
use log::{debug, error, info, warn};
use regex::Regex;

pub fn preprocess_wechat(csv_content: &str) -> String {
    let mut index_byte = 0;
    // 查找 “交易时间” 开头的行的索引，若未找到则默认从开头开始
    if let Some(line_start_index) = csv_content
        .lines()
        .position(|line| line.starts_with("交易时间"))
    {
        debug!("交易时间开始行索引: {}", line_start_index);
        for line in csv_content.lines().take(line_start_index) {
            // 累加当前行长度和换行符长度
            index_byte += line.len();
            index_byte += if csv_content[index_byte..].starts_with("\r\n") {
                2
            } else {
                1
            };
        }
        debug!("交易时间开始文字索引: {}", index_byte);
    } else {
        debug!("未找到 “交易时间” 开头的行，从文件开头开始处理");
        let index_byte: usize = 0;
        debug!("交易时间开始文字索引: {}", index_byte);
    }

    // debug!("csv_content: \n{}", csv_content[index_byte..].to_string());
    csv_content[index_byte..].to_string()
}

pub fn process_wechat(reader: &mut CsvReader) -> anyhow::Result<()> {
    // 这里可以添加预处理逻辑，例如去除空行、处理特殊字符等
    // for record in reader  {
    //     info!("record: {:#?}", record);
    // }
    // for record in reader.reader.records() {
    //     info!("record: {:#?}", record);
    // }
    //     2025-08-12 16:45:31	INFO	record: Ok(
    //     {
    //         "当前状态": "支付成功",
    //         "备注": "/",
    //         "支付方式": "中信银行(5999)",
    //         "商品": "充值50.00元",
    //         "交易时间": "2024-01-02 11:43:06",
    //         "收/支": "支出",
    //         "交易单号": "4200002079202401021659704053\t",
    //         "交易类型": "商户消费",
    //         "金额(元)": "¥50.00",
    //         "商户单号": "112591742028695654240256\t",
    //         "交易对方": "世华兄弟（重庆）餐饮管理有限公司",
    //     },
    // )

    // 交易构建示例（简化）

    for record in reader {
        info!("record: {:#?}", record);

        let line = record.unwrap();

        let date = bc::Date::from_str_unchecked(&line.get("交易时间").unwrap());
        let flag = bc::Flag::from("*");

        let payee = Some(&line.get("交易对方").unwrap());
        let narration = line.get("交易对方").unwrap();

        // 通过描述，获取账户
        let amount_type = bc::Date::from_str_unchecked(&line.get("交易类型").unwrap());
        let counterparty = bc::Date::from_str_unchecked(&line.get("交易对方").unwrap());
        let goods = bc::Date::from_str_unchecked(&line.get("商品").unwrap());
        let amount_note = bc::Date::from_str_unchecked(&line.get("备注").unwrap());
        let description = format!("{},{},{},{}", amount_type, counterparty, goods, amount_note);

        let mut account1 = String::from("");
        for rule in &common::account::DESCRIPTIONS {
            if rule.regex.is_match(description) {
                account1 = rule.account.copied();
            }
        }

        // let transaction = bc::Transaction::builder()
        //     .date(bc::Date::from_str_unchecked("2024-01-02"))
        //     .flag(bc::Flag::Okay) // 使用 * 表示已确认的交易
        //     .payee(Some("世华兄弟（重庆）餐饮管理有限公司".into()))
        //     .narration("充值50.00元 - 商户消费".into())
        //     .postings(vec![
        //         // 支出账户
        //         bc::Posting::builder()
        //             .account(
        //                 bc::Account::builder()
        //                     .ty(bc::AccountType::Assets)
        //                     .parts(vec!["Bank".into(), "CITIC".into(), "5999".into()])
        //                     .build(),
        //             )
        //             .units(
        //                 bc::IncompleteAmount::builder()
        //                     .num(Some((-50.00).into()))
        //                     .currency(Some("CNY".into()))
        //                     .build(),
        //             )
        //             .build(),
        //         // 收入账户（充值到的账户）
        //         bc::Posting::builder()
        //             .account(
        //                 bc::Account::builder()
        //                     .ty(bc::AccountType::Assets)
        //                     .parts(vec!["Digital".into(), "Prepaid".into()])
        //                     .build(),
        //             )
        //             .units(
        //                 bc::IncompleteAmount::builder()
        //                     .num(Some(50.00.into()))
        //                     .currency(Some("CNY".into()))
        //                     .build(),
        //             )
        //             .build(),
        //     ])
        //     .meta({
        //         let mut meta = bc::metadata::Meta::new();
        //         meta.insert("交易单号".into(), "4200002079202401021659704053".into());
        //         meta.insert("商户单号".into(), "112591742028695654240256".into());
        //         meta.insert("支付方式".into(), "中信银行(5999)".into());
        //         meta.insert("交易类型".into(), "商户消费".into());
        //         meta.insert("当前状态".into(), "支付成功".into());
        //         meta
        //     })
        //     .build();
    }
    Ok(())
}

pub fn get_rule() -> BillProcessRules {
    BillProcessRules {
        name_match_regex: Regex::new("微信").unwrap(),
        preprocessor: preprocess_wechat,
        processor: process_wechat,
    }
}
