# 导入函数库
from jqdata import *
from jqfactor import Factor, calc_factors
import datetime
import numpy as np

'''
基于传统财务指标的全A股价值投资策略
从全A股中选取营业收入同比增长率超过30%的股票
市净率小于4
动态市盈率小于30
市销率小于1
每个月调整一次仓位，筛选出5只股票
'''

# 初始化函数，设定基准等等
def initialize(context):
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 设定初始参数
    set_para()
    # 设定
    settings()
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')

    ## 运行函数（reference_security为运行时间的参考标的；传入的标的只做种类区分，因此传入'000300.XSHG'或'510300.XSHG'是一样的）
      # 开盘前运行
    run_monthly(before_market_open, monthday=1, time="before_open", reference_security="000300.XSHG")
      # 开盘时运行
    run_daily(stop, time="open")
    run_monthly(market_open, monthday=1, time="open", reference_security="000300.XSHG")
      # 收盘后运行
    run_monthly(after_market_close, monthday=1, time="after_close", reference_security="000300.XSHG")

def set_para():
    g.num_of_holding_stock = 5
    g.lose_rate = 0.92 
    g.gain_rate = 2
    g.blocking_days = 0
    g.lock_up_period = 10

def settings():
    # 过滤掉order系列API产生的比error级别低的log
    log.set_level('order', 'error')

    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    # set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')
    
    #将滑点和交易手续费设为0
    set_slippage(FixedSlippage(0))
    set_order_cost(OrderCost(close_tax=0, open_commission=0, close_commission=0, min_commission=0), type='stock')
    g.highest_price = {}
    g.black_list = {}

'''
================================================================================
每天开盘前
================================================================================
'''
def before_market_open(context):
    # 输出运行时间
    log.info('函数运行时间(before_market_open)：'+str(context.current_dt.time()))

    # 给微信发送消息（添加模拟交易，并绑定微信生效）
    # send_message('美好的一天~')

    # 获取2019-01-01还在上市的全部股票 
    # stocks = list(get_all_securities(types=['stock'], date="2019-01-01").index)
    #取沪深300中的股票为备选股
    SH_INDEX = get_index_stocks('000001.XSHG')
    SZ_INDEX = get_index_stocks('399001.XSHE')
    g.basket = SH_INDEX + SZ_INDEX

    # 0.获取营业收入同比增长率超过growth_threshold的股票
    growth_threshold = 0.3
    sub_basket_0 = get_inc_total_revenue_year_on_year(context, g.basket, growth_threshold)
    
    # 1.获取市净率小于pb_threshold的股票
    pb_threshold = 4.0
    sub_basket_1 = get_pb_ratio(context, g.basket, pb_threshold)

    # 2.获取动态市盈率小于pe_threshold的股票
    pe_threshold = 30.0
    sub_basket_2 = get_pe_ratio(context, g.basket, pe_threshold)
    
    # 3.获取市销率小于ps_threshold的股票
    ps_threshold = 1.0
    sub_basket_3 = get_ps_ratio(context, g.basket, ps_threshold)
    
    g.sub_basket = list(set(sub_basket_0) & set(sub_basket_1) & set(sub_basket_2) & set(sub_basket_3))

    stop(context)
    delete_from_blacklist(context)

'''
================================================================================
每天开盘时 
================================================================================
'''
def market_open(context):
    log.info('函数运行时间(market_open):' + str(context.current_dt.time()))
    g.sub_basket = filter_st_stock(g.sub_basket)
    num = len(g.sub_basket)      

    if num != 0:
        for stock in g.sub_basket[:g.num_of_holding_stock]:
            order_target_value(stock, 0)
    # 取得当前的现金
    cash = context.portfolio.available_cash
    for stock in g.sub_basket[:g.num_of_holding_stock]:
        order_value(stock, cash / g.num_of_holding_stock) 

            
'''
================================================================================
每天开盘后
================================================================================
'''
def after_market_close(context):
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('##############################################################')
    
'''
================================================================================
筛选股票条件函数
================================================================================
'''
def get_inc_total_revenue_year_on_year(context, basket, growth_threshold):
    log.info(str("获取营业收入同比增长率超过" + str(growth_threshold) + "的股票 "))
    
    #取出个股的营业收入同比增长率
    q = query(indicator.inc_total_revenue_year_on_year, indicator.code).filter(indicator.code.in_(basket))                            
    
    df = get_fundamentals(q)
    
    return list(df.loc[df["inc_total_revenue_year_on_year"] > growth_threshold]["code"])

def get_pb_ratio(context, basket, pb_threshold):
    log.info(str("获取市净率小于" + str(pb_threshold) + "的股票 "))
    
    # 取出个股的市净率
    q = query(valuation.pb_ratio, valuation.code).filter(valuation.code.in_(basket))                            
    
    df = get_fundamentals(q)
    
    return list(df.loc[(df["pb_ratio"] < pb_threshold) & (df["pb_ratio"] > 0.0)]["code"])

def get_pe_ratio(context, basket, pe_threshold):
    log.info(str("获取动态市盈率小于" + str(pe_threshold) + "的股票 "))
    
    # 取出个股的动态市盈率
    q = query(valuation.pe_ratio, valuation.code).filter(valuation.code.in_(basket))                            
    
    df = get_fundamentals(q)
    
    return(list(df.loc[(df["pe_ratio"] < pe_threshold) & (df["pe_ratio"] > 0.0)]["code"]))
    
def get_ps_ratio(context, basket, ps_threshold):
    log.info(str("获取市销率小于" + str(ps_threshold) + "的股票 "))
    
    # 取出个股的市销率
    q = query(valuation.ps_ratio, valuation.code).filter(valuation.code.in_(basket))                            
    
    df = get_fundamentals(q)
    
    return(list(df.loc[(df["ps_ratio"] < ps_threshold) & (df["ps_ratio"] >0.0)]["code"]))
    
'''
================================================================================
选股预处理 
================================================================================
'''
#剔除停牌和ST股
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused and not current_data[stock].is_st]

'''
================================================================================
风控措施  
================================================================================
'''
#止盈止损与黑名单
def stop(context):
    stock_list = list(context.portfolio.positions.keys())
    price = history(1,'1m', 'close', security_list=stock_list)
    for security in stock_list:
        price_now = price[security][-1]
        price_pre = context.portfolio.positions[security].avg_cost
        if security not in g.highest_price.keys():
            g.highest_price[security] = price_now # 该股票股价的首次跟踪记录
        elif price_now >= g.highest_price[security]:
            g.highest_price[security] = price_now # 该股票股价屡创新高
            # 从历史最高位下跌幅度超过预期 或 比上一个交易日上涨幅度超过预期
        elif price_now < g.lose_rate*g.highest_price[security] or price_now > g.gain_rate*price_pre: 
            g.black_list[security] = 0
            order_target_value(security, 0)


#黑名单剔除
def delete_from_blacklist(context):
    black_list_name = list(g.black_list.keys())
    for security in black_list_name:
        g.black_list[security]+= 1
        if g.black_list[security] > g.lock_up_period:
            del g.black_list[security]









