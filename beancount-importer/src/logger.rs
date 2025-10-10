use log::{LevelFilter, info};
use fern::Dispatch;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;
use anyhow::{Result, Context};
use chrono::Local;  // 在文件开头添加此语句

/// 初始化日志系统
pub fn init_logger(log_file: &str) -> Result<()> {
    // 确保日志目录存在
    let log_dir = Path::new(log_file).parent().context("无法获取日志文件目录")?;
    if !log_dir.exists() {
        std::fs::create_dir_all(log_dir).context("创建日志目录失败")?;
    }

    // 打开日志文件，追加模式
    let log_file = OpenOptions::new()
        .create(true)
        .write(true)
        .append(true)
        .open(log_file)
        .context("打开日志文件失败")?;

    // 配置日志调度器
    Dispatch::new()
        // 全局日志级别设置为Info
        .level(LevelFilter::Debug)
        // 针对特定模块的日志级别可以在这里设置
        // .level_for("my_module", LevelFilter::Debug)
        // 配置输出格式
        .format(|out, message, record| {
            out.finish(format_args!(
                "{}	{}	{}",
                chrono::Local::now().format("%Y-%m-%d %H:%M:%S"),
                record.level(),
                message
            ))
        })
        // 输出到文件
        .chain(log_file)
        // 也可以同时输出到标准输出
        // .chain(std::io::stdout())
        .apply()
        .context("初始化日志系统失败")?;

    info!("日志系统初始化成功");
    Ok(())
}