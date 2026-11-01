use crate::model::*;
use stratide_contracts::*;
use stratide_risk::{RiskDecision, RiskKernel};
mod cash_dividend;
mod historical;

struct FillContext<'a> {
    rules: &'a TradingRules,
    price: Cny,
    opening: Option<&'a OpeningEvidence>,
}

impl State {
    pub(crate) fn new(g: Genesis) -> Result<Self> {
        if g.provenance.source_version.trim().is_empty()
            || g.provenance.dataset_hash.trim().is_empty()
            || g.provenance.timezone != "Asia/Shanghai"
            || g.provenance.price_semantics != "unadjusted_cny_fen"
        {
            return Err("必须提供数据版本/哈希、上海时区与未复权整数分语义".into());
        }
        let snapshot = g.config.initialize(g.at, g.day)?;
        let risk = RiskKernel::new(g.config.clone())?.state().clone();
        let equity = Some(snapshot.cash);
        Ok(Self {
            config: g.config,
            provenance: g.provenance,
            snapshot,
            risk,
            orders: vec![],
            fills: vec![],
            sessions: vec![],
            equity,
            valuation_error: None,
            cash_dividends: None,
        })
    }

    fn nav(&self) -> Result<Cny> {
        let totals = self.dividend_totals()?;
        let cash_and_receivable = money(
            i64::try_from(
                i128::from(self.snapshot.cash.fen()) + i128::from(totals.receivable_fen)
                    - i128::from(totals.liability_fen),
            )
            .map_err(|_| "净资产溢出")?,
        )?;
        self.snapshot
            .positions
            .iter()
            .try_fold(cash_and_receivable, |v, l| {
                let m = self
                    .snapshot
                    .marks
                    .iter()
                    .find(|m| m.instrument == l.instrument)
                    .ok_or("持仓缺少估值")?;
                v.checked_add(m.price.checked_mul(l.quantity).map_err(|e| e.to_string())?)
                    .map_err(|e| e.to_string())
            })
    }

    fn advance(&mut self, now: Timestamp, day: TradingDay) -> Result<()> {
        if now < self.snapshot.as_of || day < self.snapshot.trading_day || !day.is_valid() {
            return Err("时间或交易日倒退/无效".into());
        }
        if day > self.snapshot.trading_day {
            if self.valuation_error.is_some() {
                return Err("前一日估值未知，不能重置日初基准".into());
            }
            self.snapshot.equity_basis.day_start_equity = self.nav()?;
            if self.snapshot.equity_basis.day_start_equity == Cny::ZERO {
                return Err("零净值不能授权新风险".into());
            }
            self.snapshot.equity_basis.net_external_flow_today_fen = 0;
        }
        self.snapshot.as_of = now;
        self.snapshot.trading_day = day;
        Ok(())
    }

    fn observe(&mut self) -> Result<()> {
        let mut kernel = self.risk_kernel()?;
        let observed = kernel.observe_account(
            &self.snapshot,
            self.snapshot.as_of,
            self.snapshot.trading_day,
        );
        self.equity = observed.as_ref().ok().copied();
        self.valuation_error = observed.err().map(|e| e.to_string());
        self.risk = kernel.state().clone();
        self.snapshot.equity_basis.cash_flow_adjusted_peak = self.risk.peak();
        Ok(())
    }

    pub(crate) fn context(
        &self,
        p: &OrderProposal,
        rules: Option<TradingRules>,
        fees: Option<&FeeSchedule>,
        bound: Option<Cny>,
    ) -> ReviewContext {
        let cost = rules.as_ref().and_then(|r| {
            let f = fees?;
            f.validate(&p.instrument, self.snapshot.trading_day).ok()?;
            let maximum_fee = bound.or_else(|| f.upper_bound(p, r).ok())?;
            Some(CostEstimate {
                proposal_id: p.proposal_id,
                proposal: p.clone(),
                rules: r.clone(),
                valid_until: p.expires_at,
                maximum_fee,
                source: format!("{} / {}", f.source, f.version),
            })
        });
        ReviewContext {
            now: self.snapshot.as_of,
            trading_day: self.snapshot.trading_day,
            rules,
            cost,
        }
    }

    pub(crate) fn apply(&mut self, cmd: &Command) -> Result<()> {
        if let Some(book) = &self.cash_dividends {
            if matches!(cmd, Command::Observe { external_flow_fen, .. } if *external_flow_fen != 0)
            {
                return Err(
                    "CASH_DIVIDEND_V1 隔离模型禁止外部资金流；股息只能走冻结事件路径".into(),
                );
            }
            if let Command::Submit { proposal, .. } = cmd {
                if book.events.iter().any(|a| {
                    a.recognized
                        && a.event.instrument == proposal.instrument
                        && proposal.decision_at < a.event.ex_at
                }) {
                    return Err("除息前旧提案不得换 ID 重放；须用除息后可信价格重新决策".into());
                }
            }
            let now = match cmd {
                Command::Observe { now, .. }
                | Command::Submit { now, .. }
                | Command::Match { now, .. }
                | Command::HistoricalNextOpenV1 { now, .. } => Some(*now),
                _ => None,
            };
            if let Some(now) = now {
                book.guard_clock(now)?;
            }
        }
        match cmd {
            Command::CashDividendV1 {
                event_id,
                phase,
                now,
                day,
                marks,
            } => {
                self.apply_dividend(event_id, phase, *now, *day, marks)?;
            }
            Command::HistoricalNextOpenV1 { now, bar, rules } => {
                self.historical_next_open(bar, rules, *now)?;
            }
            Command::Observe {
                now,
                day,
                marks,
                external_flow_fen,
            } => {
                self.advance(*now, *day)?;
                self.snapshot.marks = marks.clone();
                self.observe()?;
                if *external_flow_fen != 0 {
                    if self.valuation_error.is_some() {
                        return Err("估值未知，不能接受外部现金流调整".into());
                    }
                    let cash = money(add(self.snapshot.cash.fen(), *external_flow_fen)?)?;
                    let basis = &mut self.snapshot.equity_basis;
                    let total = add(basis.net_external_flow_total_fen, *external_flow_fen)?;
                    let funded = add(self.config.initial_capital.fen(), total)?;
                    if funded < 0 || funded > self.config.authorized_principal.fen() {
                        return Err("外部资金超出显式授权本金".into());
                    }
                    let reserved = self
                        .snapshot
                        .pending_orders
                        .iter()
                        .try_fold(0, |s, o| add(s, o.reserved_cash.fen()))?;
                    if cash.fen() < reserved {
                        return Err("出金会消耗已预留资金".into());
                    }
                    basis.net_external_flow_total_fen = total;
                    basis.net_external_flow_today_fen =
                        add(basis.net_external_flow_today_fen, *external_flow_fen)?;
                    self.snapshot.cash = cash;
                    self.observe()?;
                }
            }
            Command::Submit {
                proposal: p,
                now,
                day,
                rules,
                fees,
            } => {
                // Same ID may only ever identify the identical immutable proposal.
                if let Some(o) = self
                    .orders
                    .iter()
                    .find(|o| o.proposal.proposal_id == p.proposal_id)
                {
                    if o.proposal != *p {
                        return Err("订单 ID 已绑定不同完整提案".into());
                    }
                    return Ok(()); // Identical order retry never re-reserves or re-fills.
                }
                self.advance(*now, *day)?;
                let context = self.context(p, rules.clone(), fees.as_ref(), None);
                let mut kernel = self.risk_kernel()?;
                let decision = kernel.review(&self.snapshot, p, &context);
                self.risk = kernel.state().clone();
                self.snapshot.equity_basis.cash_flow_adjusted_peak = self.risk.peak();
                let (status, reason, reserved_fee) = match decision {
                    RiskDecision::Accepted(a) => {
                        self.snapshot.pending_orders.push(PendingOrder {
                            proposal_id: p.proposal_id,
                            instrument: p.instrument.clone(),
                            side: p.side,
                            quantity: p.quantity,
                            reserved_cash: a.maximum_cash_debit(),
                        });
                        (
                            OrderStatus::Open,
                            "最新权威状态通过风控并原子预留".into(),
                            context.cost.as_ref().unwrap().maximum_fee,
                        )
                    }
                    RiskDecision::Rejected { reason, .. } => {
                        (OrderStatus::Rejected, reason.to_string(), Cny::ZERO)
                    }
                };
                self.orders.push(PaperOrder {
                    proposal: p.clone(),
                    accepted_on: *day,
                    remaining: p.quantity,
                    status,
                    reason,
                    fee_schedule: fees.clone(),
                    reserved_fee,
                });
                self.observe()?;
            }
            Command::Match {
                now,
                day,
                instrument,
                bar,
                rules,
                opening,
            } => {
                if *now < self.snapshot.as_of || *day < self.snapshot.trading_day || !day.is_valid()
                {
                    return Err("时间或交易日倒退/无效".into());
                }
                if self.sessions.contains(&(instrument.clone(), *day)) {
                    return Err("同证券/交易日已处理，不能换事件 ID 重用流动性".into());
                }
                match self.validate_bar(instrument, *day, *now, bar.as_ref(), rules.as_ref()) {
                    Err(reason) => {
                        // Persist the failed attempt, not a completed session. In
                        // particular, do not move economic time past a later retry's
                        // opening risk observation merely because no bar arrived.
                        for order in self
                            .orders
                            .iter_mut()
                            .filter(|o| o.active() && o.proposal.instrument == *instrument)
                        {
                            order.reason = reason.clone();
                        }
                        self.observe()?;
                    }
                    Ok(()) => {
                        self.settle_session(
                            bar.as_ref().unwrap(),
                            rules.as_ref().unwrap(),
                            opening.as_ref(),
                            *now,
                        )?;
                    }
                }
            }
            Command::Freeze { scope, reason } => {
                let mut k = self.risk_kernel()?;
                k.freeze(*scope, *reason);
                self.risk = k.state().clone();
            }
        }
        self.snapshot.revision = self.snapshot.revision.checked_add(1).ok_or("版本溢出")?;
        self.validate()
    }

    fn validate_bar(
        &self,
        instrument: &Instrument,
        day: TradingDay,
        now: Timestamp,
        bar: Option<&DailyBar>,
        rules: Option<&TradingRules>,
    ) -> Result<()> {
        let b = bar.ok_or("缺行情，保持未成交")?;
        let r = rules.ok_or("缺交易规则/停牌/价格带证据，保持未成交")?;
        if b.provenance != self.provenance
            || b.instrument != *instrument
            || b.day != day
            || b.opens_at.0 < 0
            || b.opens_at >= b.closes_at
            || b.closes_at > b.available_at
            || b.available_at > now
            || now.0 - b.closes_at.0 > self.config.max_mark_age_ms
            || !b.status_verified
            || r.instrument != *instrument
            || r.trading_day != day
            || r.available_at > now
            || r.available_at.0 < 0
            || now.0 - r.available_at.0 > self.config.max_snapshot_age_ms
            || r.source.trim().is_empty()
            || r.tick_size == Cny::ZERO
            || r.min_price == Cny::ZERO
            || r.max_price < r.min_price
            || r.buy_lot <= 0
            || r.sell_lot <= 0
            || b.volume_shares <= 0
            || b.capacity_shares < 0
            || b.capacity_shares > b.volume_shares
            || b.low > b.high
            || b.open < b.low
            || b.open > b.high
            || b.close < b.low
            || b.close > b.high
            || [b.open, b.high, b.low, b.close]
                .iter()
                .any(|p| *p < r.min_price || *p > r.max_price || p.fen() % r.tick_size.fen() != 0)
        {
            return Err("行情/时效/来源/停牌/一字板/价格带证据不支持撮合".into());
        }
        Ok(())
    }

    fn validate_opening(
        &self,
        b: &DailyBar,
        rules: &TradingRules,
        opening: Option<&OpeningEvidence>,
    ) -> Result<()> {
        let e = opening.ok_or("缺独立开盘证据，不反推盘中执行资格")?;
        if self.snapshot.as_of > b.opens_at {
            return Err("已有晚于开盘的已提交状态，不能回溯改变当日执行".into());
        }
        let mut compatible = rules.clone();
        compatible.available_at = e.rules.available_at;
        compatible.source = e.rules.source.clone();
        // A later suspension may conservatively invalidate fills, but its later
        // status is not an opening NAV/financial-lock observation.
        compatible.tradable = e.rules.tradable;
        if compatible != e.rules
            || e.rules.available_at > b.opens_at
            || e.rules.available_at.0 < 0
            || b.opens_at.0 - e.rules.available_at.0 > self.config.max_snapshot_age_ms
            || e.rules.source.trim().is_empty()
            || !e
                .marks
                .iter()
                .any(|m| m.instrument == b.instrument && m.price == b.open)
            || e.marks.iter().any(|m| {
                m.as_of.0 < 0
                    || m.as_of > m.available_at
                    || m.available_at > b.opens_at
                    || b.opens_at.0 - m.as_of.0 > self.config.max_mark_age_ms
                    || m.source.trim().is_empty()
            })
        {
            return Err("开盘估值/规则不完整、陈旧、未来或与日线不相容".into());
        }
        Ok(())
    }

    fn settle_session(
        &mut self,
        b: &DailyBar,
        rules: &TradingRules,
        opening: Option<&OpeningEvidence>,
        accounted_at: Timestamp,
    ) -> Result<()> {
        let eligibility = self.validate_opening(b, rules, opening);
        if eligibility.is_ok() {
            let e = opening.unwrap();
            self.advance(b.opens_at, b.day)?;
            self.snapshot.marks = e.marks.clone();
            self.observe()?;
        }
        let mut capacity = b.capacity_shares;
        for index in 0..self.orders.len() {
            if !self.orders[index].active()
                || self.orders[index].proposal.instrument != b.instrument
            {
                continue;
            }
            if b.opens_at >= self.orders[index].proposal.expires_at {
                self.expire(index);
                continue;
            }
            // Unordered full-day extrema cannot prove a crossing before an
            // intraday/exact-close expiry. Keep its reservation during every
            // opening review; releasing it now would also leak future expiry.
            if self.orders[index].proposal.expires_at <= b.closes_at {
                self.orders[index].reason =
                    "有效期未覆盖完整日线，不能证明到期前穿越；预留待到期结算".into();
                continue;
            }
            if let Err(reason) = &eligibility {
                self.orders[index].reason = reason.clone();
                continue;
            }
            if !rules.tradable {
                self.orders[index].reason = "时段停牌证据，保持未成交".into();
                continue;
            }
            let before_order = self.clone();
            let before_capacity = capacity;
            if let Err(error) =
                self.match_order(index, b, opening.unwrap(), accounted_at, &mut capacity)
            {
                *self = before_order;
                capacity = before_capacity;
                let mut kernel = self.risk_kernel()?;
                kernel.freeze(
                    stratide_risk::RiskScope::Account,
                    stratide_risk::FreezeReason::Manual,
                );
                self.risk = kernel.state().clone();
                self.orders[index].reason =
                    format!("模拟会计失败，保持原预留并冻结等待人工检查：{error}");
            }
        }
        // Opening risk qualification is not a proven execution timestamp. The
        // model uses the WHOLE session; observe closing NAV only after settling
        // eligible model fills, without retrospectively selecting them by close.
        self.advance(accounted_at, b.day)?;
        self.snapshot.marks.retain(|m| m.instrument != b.instrument);
        self.snapshot.marks.push(PositionMark {
            instrument: b.instrument.clone(),
            price: b.close,
            as_of: b.closes_at,
            available_at: b.available_at,
            source: b.provenance.source_version.clone(),
        });
        for index in 0..self.orders.len() {
            if self.orders[index].active()
                && self.orders[index].proposal.instrument == b.instrument
                && accounted_at >= self.orders[index].proposal.expires_at
            {
                self.expire(index);
                if b.opens_at < self.orders[index].proposal.expires_at
                    && self.orders[index].proposal.expires_at <= b.closes_at
                {
                    self.orders[index].reason =
                        "已到期，有效期未覆盖完整日线，不能证明到期前穿越；释放剩余预留".into();
                }
            }
        }
        self.sessions.push((b.instrument.clone(), b.day));
        self.observe()
    }

    fn expire(&mut self, index: usize) {
        self.orders[index].status = OrderStatus::Expired;
        self.orders[index].reserved_fee = Cny::ZERO;
        self.orders[index].reason = "到期，释放剩余预留；不是超时未知成交".into();
        self.remove_pending(index);
    }

    fn remove_pending(&mut self, index: usize) {
        let id = self.orders[index].proposal.proposal_id;
        self.snapshot.pending_orders.retain(|o| o.proposal_id != id);
    }

    fn match_order(
        &mut self,
        index: usize,
        b: &DailyBar,
        opening: &OpeningEvidence,
        accounted_at: Timestamp,
        capacity: &mut i64,
    ) -> Result<()> {
        let r = &opening.rules;
        let order = self.orders[index].clone();
        let p = order.proposal.clone();
        if !r.tradable || r.settlement == SettlementRule::Unknown || b.low == b.high {
            self.orders[index].reason = "停牌、未知交收或一字板：估值可观察，保持未成交".into();
            return Ok(());
        }
        // Close-derived signals can only participate in a later trusted session.
        // Strict crossing at the original limit is a declared model, never proof
        // that an OHLC touch was executable. No favorable open-price improvement.
        if order.accepted_on >= b.day
            || p.decision_at >= b.opens_at
            || p.earliest_execution_at > b.opens_at
            || p.limit_price <= b.low
            || p.limit_price >= b.high
            || p.limit_price <= r.min_price
            || p.limit_price >= r.max_price
            || (p.side == Side::Buy && b.open > p.limit_price)
            || (p.side == Side::Sell && b.open < p.limit_price)
        {
            self.orders[index].reason = "非后续时段、仅触价、开盘不利或封板边界，保持未成交".into();
            return Ok(());
        }
        self.fill_order(
            index,
            b,
            accounted_at,
            capacity,
            FillContext {
                rules: r,
                price: p.limit_price,
                opening: Some(opening),
            },
        )
    }

    fn fill_order(
        &mut self,
        index: usize,
        b: &DailyBar,
        accounted_at: Timestamp,
        capacity: &mut i64,
        execution: FillContext<'_>,
    ) -> Result<()> {
        let r = execution.rules;
        let order = self.orders[index].clone();
        let mut p = order.proposal.clone();
        p.quantity = order.remaining;
        let schedule = order.fee_schedule.as_ref().ok_or("已接受订单缺费率")?;
        if schedule.validate(&p.instrument, b.day).is_err()
            || !schedule
                .upper_bound(&p, r)
                .is_ok_and(|bound| bound <= order.reserved_fee)
        {
            self.orders[index].reason = "费用有效期/原预留上界不足，保持未成交".into();
            return Ok(());
        }
        if self.valuation_error.is_some() {
            self.orders[index].reason = "全账户估值未知，保持未成交".into();
            return Ok(());
        }
        // Remove ONLY this order's reservation in a private draft; other orders'
        // commitments remain visible to the mandatory review of the latest state.
        let mut available = self.snapshot.clone();
        available
            .pending_orders
            .retain(|o| o.proposal_id != p.proposal_id);
        let c = self.context(
            &p,
            Some(r.clone()),
            Some(schedule),
            Some(order.reserved_fee),
        );
        let mut kernel = self.risk_kernel()?;
        let decision = kernel.review(&available, &p, &c);
        self.risk = kernel.state().clone();
        self.snapshot.equity_basis.cash_flow_adjusted_peak = self.risk.peak();
        if let RiskDecision::Rejected { reason, .. } = decision {
            self.orders[index].reason = format!("执行前风控拒绝：{reason}");
            return Ok(());
        }
        let lot = if p.side == Side::Buy {
            r.buy_lot
        } else {
            r.sell_lot
        };
        let mut quantity = (*capacity).min(order.remaining);
        if quantity != order.remaining || p.side == Side::Buy || !r.allow_odd_lot_liquidation {
            quantity -= quantity % lot;
        }
        if quantity <= 0 {
            self.orders[index].reason = "保守流动性额度不足整手，保持未成交".into();
            return Ok(());
        }
        let gross = execution
            .price
            .checked_mul(quantity)
            .map_err(|e| e.to_string())?;
        let fees = schedule.fees(gross, p.side)?;
        let total_fee = fees.total()?;
        let debit = gross.checked_add(total_fee).map_err(|e| e.to_string())?;
        if total_fee > order.reserved_fee {
            return Err("实付费用超过已预留上界".into());
        }
        match p.side {
            Side::Buy => {
                self.snapshot.cash = money(
                    self.snapshot
                        .cash
                        .fen()
                        .checked_sub(debit.fen())
                        .ok_or("现金溢出")?,
                )?;
                self.snapshot.positions.push(PositionLot {
                    instrument: p.instrument.clone(),
                    quantity,
                    acquired_on: b.day,
                });
            }
            Side::Sell => {
                let proceeds = gross
                    .fen()
                    .checked_sub(total_fee.fen())
                    .filter(|v| *v >= 0)
                    .ok_or("费用超过卖出金额")?;
                self.snapshot.cash = money(add(self.snapshot.cash.fen(), proceeds)?)?;
                let mut left = quantity;
                for l in &mut self.snapshot.positions {
                    if l.instrument == p.instrument
                        && (r.settlement == SettlementRule::SameDay || l.acquired_on < b.day)
                    {
                        let take = left.min(l.quantity);
                        l.quantity -= take;
                        left -= take;
                    }
                }
                if left != 0 {
                    return Err("可卖持仓不足，整个事务回滚".into());
                }
                self.snapshot.positions.retain(|l| l.quantity > 0);
            }
        }
        *capacity -= quantity;
        self.remove_pending(index);
        let o = &mut self.orders[index];
        o.remaining -= quantity;
        o.reserved_fee = if o.remaining == 0 {
            Cny::ZERO
        } else {
            money(o.reserved_fee.fen() - total_fee.fen())?
        };
        o.status = if o.remaining == 0 {
            OrderStatus::Filled
        } else {
            OrderStatus::PartiallyFilled
        };
        o.reason = if execution.opening.is_some() {
            "保守日线限价穿越模型模拟成交；不是交易所成交"
        } else {
            "historical_ex_post_execution_assumption：next-open 不利一跳；非实时实收或真实成交"
        }
        .into();
        if o.remaining > 0 {
            self.snapshot.pending_orders.push(PendingOrder {
                proposal_id: p.proposal_id,
                instrument: p.instrument.clone(),
                side: p.side,
                quantity: o.remaining,
                reserved_cash: if p.side == Side::Buy {
                    p.limit_price
                        .checked_mul(o.remaining)
                        .and_then(|v| v.checked_add(o.reserved_fee))
                        .map_err(|e| e.to_string())?
                } else {
                    Cny::ZERO
                },
            });
        }
        self.fills.push(Fill {
            event_id: format!("{}:{}", b.day.0, p.proposal_id.0),
            order_id: p.proposal_id,
            instrument: p.instrument,
            side: p.side,
            quantity,
            price: execution.price,
            fees,
            day: b.day,
            simulated_at: accounted_at,
            risk_checked_at: self.snapshot.as_of,
            opening_evidence: execution.opening.cloned(),
            historical_execution: execution.opening.is_none().then(|| {
                "historical_ex_post_execution_assumption/next-open-adverse-tick-100-v1".into()
            }),
            evidence: b.clone(),
            fee_version: schedule.version.clone(),
        });
        // Capture fee-driven losses immediately, even between fills in one session.
        self.observe()
    }

    pub(crate) fn validate(&self) -> Result<()> {
        let mut expected_cash = i128::from(self.config.initial_capital.fen())
            + i128::from(self.snapshot.equity_basis.net_external_flow_total_fen);
        expected_cash += i128::from(self.dividend_totals()?.cash_paid_fen);
        let mut quantities: Vec<(Instrument, i64)> = vec![];
        for f in &self.fills {
            let gross = i128::from(f.price.fen()) * i128::from(f.quantity);
            expected_cash += if f.side == Side::Buy { -gross } else { gross };
            expected_cash -= i128::from(f.fees.total()?.fen());
            let delta = if f.side == Side::Buy {
                f.quantity
            } else {
                -f.quantity
            };
            if let Some((_, q)) = quantities.iter_mut().find(|(i, _)| *i == f.instrument) {
                *q = add(*q, delta)?;
            } else {
                quantities.push((f.instrument.clone(), delta));
            }
        }
        if expected_cash != i128::from(self.snapshot.cash.fen()) {
            return Err("现金/成交/费用/外部流量不守恒".into());
        }
        for (i, q) in &quantities {
            let held = self
                .snapshot
                .positions
                .iter()
                .filter(|l| l.instrument == *i)
                .try_fold(0, |s, l| add(s, l.quantity))?;
            if held != *q || held < 0 {
                return Err("整数持仓不守恒".into());
            }
        }
        for lot in &self.snapshot.positions {
            if lot.quantity <= 0 || !quantities.iter().any(|(i, _)| *i == lot.instrument) {
                return Err("无成交来源的持仓".into());
            }
        }
        let mut expected = vec![];
        for o in self.orders.iter().filter(|o| o.active()) {
            if o.remaining <= 0 {
                return Err("未完成订单数量错误".into());
            }
            expected.push(PendingOrder {
                proposal_id: o.proposal.proposal_id,
                instrument: o.proposal.instrument.clone(),
                side: o.proposal.side,
                quantity: o.remaining,
                reserved_cash: if o.proposal.side == Side::Buy {
                    o.proposal
                        .limit_price
                        .checked_mul(o.remaining)
                        .and_then(|v| v.checked_add(o.reserved_fee))
                        .map_err(|e| e.to_string())?
                } else {
                    Cny::ZERO
                },
            });
        }
        expected.sort_by_key(|p| p.proposal_id.0);
        let mut actual = self.snapshot.pending_orders.clone();
        actual.sort_by_key(|p| p.proposal_id.0);
        if expected != actual {
            return Err("订单/资金/股份预留不一致".into());
        }
        let reserved = actual
            .iter()
            .try_fold(0, |v, o| add(v, o.reserved_cash.fen()))?;
        if reserved > self.snapshot.cash.fen() {
            return Err("现金预留超额".into());
        }
        Ok(())
    }
}
