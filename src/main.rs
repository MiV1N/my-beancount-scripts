// 由于 `files` 模块未定义，这里暂时注释掉该导入语句，需确保 `files` 模块存在或使用正确的模块名
mod files;
mod logger;
// use beancount_importer::files::CsvReader;
use anyhow;
use files::{BillFiles, BillProcessRules, CsvReader};
use log::{debug, error, info, warn};
use logger::init_logger;
use regex::Regex;

fn preprocess_wechat(csv_content: &str) -> String {
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

fn process_wechat(reader: &mut CsvReader) -> anyhow::Result<()> {
    // 这里可以添加预处理逻辑，例如去除空行、处理特殊字符等
    // for record in reader  {
    //     info!("record: {:#?}", record);
    // }
    for record in reader.reader.records() {
        info!("record: {:#?}", record);
    }
    Ok(())
}

fn main() {
    // 初始化日志系统
    if let Err(e) = init_logger("logs/app.log") {
        eprintln!("初始化日志系统失败: {}", e);
        return;
    }

    // 使用测试数据目录
    let billfiles_result = BillFiles::new("test_datas");

    let Ok(mut billfiles) = billfiles_result else {
        error!("初始化BillFiles失败: {}", billfiles_result.unwrap_err());
        return;
    };

    for file in billfiles.iter() {
        info!("发现文件: {}", file);
    }

    let wechat_rule = BillProcessRules {
        name_match_regex: Regex::new("微信").unwrap(),
        preprocessor: preprocess_wechat,
        processor: process_wechat,
    };

    if let Err(e) = billfiles.regist_processor(wechat_rule) {
        error!("注册处理器失败: {}", e);
        return;
    }

    if let Err(e) = billfiles.process() {
        error!("处理文件失败: {}", e);
        return;
    }

    // println!("billfiles: {:#?}", billfiles);
}
