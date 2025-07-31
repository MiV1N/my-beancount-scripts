use crate::files::{BillProcessRules, CsvReader};
use log::{debug, error, info, warn};
use regex::Regex;

pub fn preprocess_citi(csv_content: &str) -> String {
    let mut index_byte = 0;
    // 查找 “交易时间” 开头的行的索引，若未找到则默认从开头开始
    if let Some(line_start_index) = csv_content
        .lines()
        .position(|line| line.starts_with("交易日期"))
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

pub fn process_citi(reader: &mut CsvReader) -> anyhow::Result<()> {
    // 这里可以添加预处理逻辑，例如去除空行、处理特殊字符等
    // for record in reader  {
    //     info!("record: {:#?}", record);
    // }
    // for record in reader.reader.records() {
    //     info!("record: {:#?}", record);
    // }

    for record in reader {
        info!("record: {:#?}", record);
    }
    Ok(())
}

pub fn get_rule() -> BillProcessRules {
    BillProcessRules {
        name_match_regex: Regex::new("中信").unwrap(),
        preprocessor: preprocess_citi,
        processor: process_citi,
    }
}
