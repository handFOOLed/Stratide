use super::*;
use crate::portfolio::*;
use std::collections::BTreeSet;

fn valid_sha(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|c| c.is_ascii_hexdigit())
}
fn next_day(d: TradingDay) -> Result<TradingDay> {
    use chrono::Datelike;
    let date = chrono::NaiveDate::from_ymd_opt((d.0 / 10000) as i32, d.0 / 100 % 100, d.0 % 100)
        .ok_or("INVALID_CALENDAR_DATE")?
        .succ_opt()
        .ok_or("INVALID_CALENDAR_DATE")?;
    Ok(TradingDay(
        date.year() as u32 * 10000 + date.month() * 100 + date.day(),
    ))
}
fn target(d: &Decision) -> Result<TradingDay> {
    if !valid_sha(&d.calendar_sha256)
        || d.calendar_received_at > d.now
        || d.calendar.is_empty()
        || d.calendar.len() > 40
    {
        return Err("CALENDAR_MISSING_OR_FUTURE".into());
    }
    let mut expected = d.day;
    for row in &d.calendar {
        if row.day != expected
            || row.sse_open != row.szse_open
            || (row.day == d.day && !row.sse_open)
        {
            return Err("CALENDAR_GAP_CONFLICT_OR_CLOSED_DECISION_DAY".into());
        }
        if row.day > d.day && row.sse_open {
            return Ok(row.day);
        }
        expected = next_day(expected)?;
    }
    Err("NEXT_TRADING_SESSION_UNKNOWN".into())
}
fn supported_rules(r: &TradingRules) -> bool {
    // Explicit supported slice: mature ordinary SSE/SZSE main board shares.
    // STAR/ChiNext/BSE remain visible but cannot inherit main-board rules.
    ((r.instrument.market == Market::Shanghai && r.instrument.code.starts_with("60"))
        || (r.instrument.market == Market::Shenzhen && r.instrument.code.starts_with("00")))
        && r.settlement == SettlementRule::TPlusOne
        && r.buy_lot == 100
        && r.sell_lot == 100
        && r.tick_size.fen() == 1
        && r.min_price > Cny::ZERO
        && r.max_price > r.min_price
        && !r.source.trim().is_empty()
}

impl State {
    pub(super) fn configure_portfolio(&mut self, now: Timestamp, p: &Policy) -> Result<()> {
        if self.portfolio.is_some()
            || self.paper_eod.as_ref().is_some_and(|b| b.pending.is_some())
            || self.orders.iter().any(PaperOrder::active)
            || self.cash_dividends.is_some()
            || !self
                .provenance
                .source_version
                .starts_with("paper-eod-assumption-v1")
            || now < self.snapshot.as_of
            || p.version != crate::portfolio::VERSION
            || !p.approve_fixed_baseline
            || p.universe.is_empty()
            || p.universe.len() > 6000
            || p.universe.iter().any(|i| !i.is_valid())
            || p.universe
                .iter()
                .map(|i| format!("{:?}:{}", i.market, i.code))
                .collect::<BTreeSet<_>>()
                .len()
                != p.universe.len()
            || p.max_positions == 0
            || p.max_positions > 100
            || p.max_candidates == 0
            || p.max_candidates > 100
            || p.max_daily_orders == 0
            || p.max_daily_orders > 100
            || p.max_order_shares <= 0
            || p.max_order_shares % 100 != 0
            || p.capacity_shares <= 0
            || p.capacity_shares % 100 != 0
            || p.target_value == Cny::ZERO
            || p.target_value > p.max_symbol_value
            || p.max_symbol_value > self.config.strategy_limits.max_exposure
            || p.max_daily_fees == Cny::ZERO
            || p.slippage_bps > 1000
            || p.min_amount_thousand_yuan == 0
            || p.fees.len() != p.universe.len()
        {
            return Err("OWNER_PORTFOLIO_POLICY_INVALID_OR_ALREADY_FROZEN".into());
        }
        for i in &p.universe {
            let fees = p
                .fees
                .iter()
                .filter(|f| f.instrument == *i)
                .collect::<Vec<_>>();
            if fees.len() != 1 {
                return Err("OWNER_FEE_SCHEDULE_REQUIRED_PER_SECURITY".into());
            }
            fees[0].validate(i, crate::paper_eod::shanghai_day(now)?.0)?;
        }
        self.portfolio = Some(Book {
            policy: p.clone(),
            approved_at: now,
            automatic: p.automatic,
            pending: None,
            batches: vec![],
            last_event_at: now,
        });
        Ok(())
    }

    pub(super) fn freeze_portfolio(&mut self, d: &Decision) -> Result<()> {
        let book = self
            .portfolio
            .as_ref()
            .ok_or("OWNER_PORTFOLIO_POLICY_REQUIRED")?;
        if !book.automatic
            || book.pending.is_some()
            || self.orders.iter().any(PaperOrder::active)
            || book.batches.iter().any(|b| b.decision.day == d.day)
            || d.now < self.snapshot.as_of
            || d.now < book.approved_at
            || d.now < session(d.day, 8, 0)?
        {
            return Err("PORTFOLIO_DECISION_WINDOW_PAUSE_OR_DUPLICATE".into());
        }
        let (local_day, _) = crate::paper_eod::shanghai_day(d.now)?;
        if local_day != d.day
            || !valid_sha(&d.source_sha256)
            || d.received_at > d.now
            || d.received_at < session(d.day, 8, 0)?
            || d.securities.len() > 6000
            || d.securities
                .iter()
                .map(|s| format!("{:?}:{}", s.instrument.market, s.instrument.code))
                .collect::<BTreeSet<_>>()
                .len()
                != d.securities.len()
        {
            return Err("PORTFOLIO_SOURCE_TIME_OR_SECURITIES_INVALID".into());
        }
        let p = book.policy.clone();
        let mut batch = Batch {
            decision: d.clone(),
            target_day: None,
            policy_sha256: digest(&p),
            label: LABEL.into(),
            reason: String::new(),
            proposal_ids: vec![],
            rejections: vec![],
            finalized_at: None,
            confirmation: None,
        };
        // A missing calendar/source/research produces an auditable cash-only batch.
        let admission = (|| -> Result<TradingDay> {
            let day = target(d)?;
            if !d.source_ready {
                return Err(format!("SOURCE_BLOCKED:{}", d.reason));
            }
            let r = d
                .research
                .as_ref()
                .ok_or("RESEARCH_NOT_READY_84_SESSIONS_REQUIRED")?;
            if r.ready_sessions < 84
                || r.restriction != "RESEARCH_ONLY"
                || r.eligibility != "ELIGIBILITY_DENIED"
                || r.can_execute_forward_paper
                || !valid_sha(&r.candidate_sha256)
                || !valid_sha(&r.registration_sha256)
                || r.task_id.is_empty()
                || r.model_version.is_empty()
                || r.selected.len() > p.max_candidates
                || r.selected
                    .iter()
                    .map(|i| format!("{:?}:{}", i.market, i.code))
                    .collect::<BTreeSet<_>>()
                    .len()
                    != r.selected.len()
            {
                return Err("RESEARCH_EVIDENCE_OR_CAPACITY_INVALID".into());
            }
            if r.generated_at < d.received_at
                || r.finished_at < r.generated_at
                || r.finished_at > d.now
                || r.finished_at >= session(day, 1, 30)?
            {
                return Err("LATE_RESEARCH_ONLY".into());
            }
            Ok(day)
        })();
        match admission {
            Err(reason) => {
                batch.reason = reason;
                batch.finalized_at = Some(d.now);
            }
            Ok(day) => {
                batch.target_day = Some(day);
                self.advance(d.now, d.day)?;
                // T marks only. RiskKernel validates complete account valuation.
                if d.marks
                    .iter()
                    .any(|m| m.as_of > d.now || m.available_at > d.now)
                {
                    return Err("FUTURE_DECISION_MARK".into());
                }
                self.snapshot.marks = d.marks.clone();
                self.observe()?;
                let selected = &d.research.as_ref().expect("admitted research").selected;
                let mut instruments = selected.clone();
                for lot in &self.snapshot.positions {
                    if !instruments.contains(&lot.instrument) {
                        instruments.push(lot.instrument.clone());
                    }
                }
                // Sell then buy, market/code ascending, frozen before next-day quotes.
                instruments.sort_by_key(|i| (format!("{:?}", i.market), i.code.clone()));
                instruments.dedup();
                let mut compiled = Vec::new();
                for i in instruments {
                    let security = d.securities.iter().find(|s| s.instrument == i);
                    let s = match security {
                        Some(s)
                            if p.universe.contains(&i)
                                && s.supported
                                && supported_rules(&s.rules)
                                && s.rules.instrument == i
                                && s.rules.trading_day == d.day
                                && s.rules.available_at <= d.now
                                && s.rules.tradable
                                && s.close > Cny::ZERO
                                && s.amount_thousand_yuan >= p.min_amount_thousand_yuan =>
                        {
                            s
                        }
                        _ => {
                            batch
                                .rejections
                                .push((i, "UNSUPPORTED_PAPER_OR_MISSING_TRUSTED_RULES".into()));
                            continue;
                        }
                    };
                    let held: i64 = self
                        .snapshot
                        .positions
                        .iter()
                        .filter(|l| l.instrument == i)
                        .map(|l| l.quantity)
                        .sum();
                    let desired = if selected.contains(&i) {
                        p.target_value.fen() / s.close.fen() / 100 * 100
                    } else {
                        0
                    };
                    let delta = desired - held;
                    if delta == 0 {
                        continue;
                    }
                    let side = if delta > 0 { Side::Buy } else { Side::Sell };
                    let qty = delta.abs().min(p.max_order_shares) / 100 * 100;
                    if qty == 0 {
                        continue;
                    }
                    let bps = i64::from(p.slippage_bps);
                    let limit = money(if side == Side::Buy {
                        i64::try_from(
                            i128::from(s.close.fen())
                                + (i128::from(s.close.fen()) * i128::from(bps) + 9999) / 10000,
                        )
                        .map_err(|_| "PORTFOLIO_PRICE_OVERFLOW")?
                    } else {
                        i64::try_from(
                            i128::from(s.close.fen())
                                - i128::from(s.close.fen()) * i128::from(bps) / 10000,
                        )
                        .map_err(|_| "PORTFOLIO_PRICE_OVERFLOW")?
                    })?;
                    if side == Side::Buy
                        && limit.checked_mul(held + qty).map_err(|e| e.to_string())?
                            > p.max_symbol_value
                    {
                        batch.rejections.push((i, "MAX_SYMBOL_VALUE".into()));
                        continue;
                    }
                    compiled.push((side, qty, limit, s.clone()));
                }
                compiled.sort_by_key(|(side, _, _, s)| {
                    (
                        if *side == Side::Sell { 0 } else { 1 },
                        format!("{:?}", s.instrument.market),
                        s.instrument.code.clone(),
                    )
                });
                let mut slots: Vec<_> = self
                    .snapshot
                    .positions
                    .iter()
                    .map(|l| l.instrument.clone())
                    .collect();
                slots.sort_by_key(|i| format!("{:?}:{}", i.market, i.code));
                slots.dedup();
                let mut fee_budget = 0_i64;
                for (side, quantity, limit_price, s) in compiled {
                    if batch.proposal_ids.len() >= p.max_daily_orders
                        || (side == Side::Buy
                            && !slots.contains(&s.instrument)
                            && slots.len() >= p.max_positions)
                    {
                        batch
                            .rejections
                            .push((s.instrument, "DAILY_ORDER_OR_POSITION_CAP".into()));
                        continue;
                    }
                    let mut proposal = OrderProposal {
                        proposal_id: ProposalId(1),
                        account_id: self.config.account_id.clone(),
                        deployment: self.config.deployment.clone(),
                        instrument: s.instrument.clone(),
                        side,
                        quantity,
                        limit_price,
                        decision_at: d.now,
                        data_available_at: d.received_at,
                        earliest_execution_at: session(day, 1, 30)?,
                        expires_at: deadline(day)?,
                    };
                    // IDs bind policy/day/security/direction; retries with fresh event IDs cannot reserve twice.
                    let hash = digest(&(
                        batch.policy_sha256.clone(),
                        d.day,
                        &proposal.instrument,
                        side,
                    ));
                    proposal.proposal_id =
                        ProposalId(u128::from_str_radix(&hash[..16], 16).expect("SHA prefix"));
                    let fees = p
                        .fees
                        .iter()
                        .find(|f| f.instrument == s.instrument)
                        .expect("validated policy fees");
                    if fees.validate(&s.instrument, day).is_err() {
                        batch.rejections.push((s.instrument, "COST_UNKNOWN".into()));
                        continue;
                    }
                    let bound = fees.upper_bound(&proposal, &s.rules)?.fen();
                    if add(fee_budget, bound)? > p.max_daily_fees.fen() {
                        batch
                            .rejections
                            .push((s.instrument, "DAILY_FEE_CAP".into()));
                        continue;
                    }
                    self.submit_order(
                        &proposal,
                        d.now,
                        d.day,
                        &Some(s.rules),
                        &Some(fees.clone()),
                    )?;
                    let order = self.orders.last().expect("submitted order");
                    if order.active() {
                        fee_budget = add(fee_budget, bound)?;
                        if !slots.contains(&s.instrument) {
                            slots.push(s.instrument);
                        }
                    }
                    batch.proposal_ids.push(proposal.proposal_id);
                }
                if !self.orders.iter().any(PaperOrder::active) {
                    batch.finalized_at = Some(d.now);
                    batch.reason = "CASH_ONLY_OR_RISK_REJECTED".into();
                } else {
                    batch.reason = "FROZEN_SELL_THEN_MARKET_CODE_FIXED_TICKET".into();
                }
            }
        }
        let book = self.portfolio.as_mut().expect("configured book");
        if batch.finalized_at.is_none() {
            book.pending = Some(book.batches.len());
        }
        book.batches.push(batch);
        book.last_event_at = d.now;
        Ok(())
    }

    pub(super) fn confirm_portfolio(&mut self, c: &Confirmation) -> Result<()> {
        let book = self.portfolio.as_ref().ok_or("PORTFOLIO_NOT_CONFIGURED")?;
        let index = book.pending.ok_or("NO_PENDING_PORTFOLIO_BATCH")?;
        let batch = book.batches[index].clone();
        let day = batch.target_day.expect("pending target day");
        let opens = session(day, 1, 30)?;
        let closes = session(day, 7, 0)?;
        let end = deadline(day)?;
        if c.day != day
            || c.now < session(day, 8, 0)?
            || !valid_sha(&c.source_sha256)
            || c.received_at > c.now
            || c.quotes.len() > 6000
            || c.quotes
                .iter()
                .map(|q| format!("{:?}:{}", q.bar.instrument.market, q.bar.instrument.code))
                .collect::<BTreeSet<_>>()
                .len()
                != c.quotes.len()
        {
            return Err("PORTFOLIO_CONFIRMATION_TIME_OR_SOURCE_INVALID".into());
        }
        let capacity = book.policy.capacity_shares;
        let timely = c.now < end && c.received_at >= session(day, 8, 0)? && c.received_at < end;
        for q in &c.quotes {
            let b = &q.bar;
            if b.day != day
                || b.provenance != self.provenance
                || b.opens_at != opens
                || b.closes_at != closes
                || b.available_at > c.received_at
                || b.available_at < session(day, 8, 0)?
                || q.rules.instrument != b.instrument
                || q.rules.trading_day != day
                || q.rules.available_at > c.now
            {
                return Err("PORTFOLIO_QUOTE_IDENTITY_OR_FUTURE_SOURCE".into());
            }
        }
        if timely {
            // Observe the WHOLE account at one modeled opening before reviewing
            // any order. Never expose T+1 close/high/low to fill risk/priority.
            self.advance(opens, day)?;
            self.snapshot.marks = c
                .quotes
                .iter()
                .filter(|q| {
                    q.corporate_actions_verified && q.bar.status_verified && q.bar.open > Cny::ZERO
                })
                .map(|q| PositionMark {
                    instrument: q.bar.instrument.clone(),
                    price: q.bar.open,
                    as_of: opens,
                    available_at: opens,
                    source: "EX_POST_OPEN_ASSUMPTION/whole-account".into(),
                })
                .collect();
            self.observe()?;
        }
        for id in &batch.proposal_ids {
            let oi = self
                .orders
                .iter()
                .position(|o| o.proposal.proposal_id == *id)
                .expect("frozen proposal");
            if !self.orders[oi].active() {
                continue;
            }
            let proposal = self.orders[oi].proposal.clone();
            let quote = c
                .quotes
                .iter()
                .find(|q| q.bar.instrument == proposal.instrument);
            let mut reason = if timely {
                "NO_FILL / MISSING_QUOTE"
            } else {
                "NO_FILL / EXPIRED_DELIVERY_WINDOW"
            }
            .to_string();
            if timely {
                if let Some(q) = quote {
                    let price = i64::try_from(
                        i128::from(q.bar.open.fen())
                            + if proposal.side == Side::Buy { 1 } else { -1 },
                    )
                    .map_err(|_| "PORTFOLIO_PRICE_OVERFLOW".to_string())
                    .and_then(money);
                    if q.corporate_actions_verified
                        && q.bar.status_verified
                        && supported_rules(&q.rules)
                        && q.rules.tradable
                        && q.bar.open > q.rules.min_price
                        && q.bar.open < q.rules.max_price
                        && price.as_ref().is_ok_and(|v| {
                            *v > q.rules.min_price
                                && *v < q.rules.max_price
                                && if proposal.side == Side::Buy {
                                    *v <= proposal.limit_price
                                } else {
                                    *v >= proposal.limit_price
                                }
                        })
                    {
                        let mut rules = q.rules.clone();
                        rules.available_at = opens;
                        rules.source = format!("EX_POST_OPEN_ASSUMPTION | {}", rules.source);
                        let mut remaining_capacity = capacity;
                        let before = self.fills.len();
                        self.fill_order(
                            oi,
                            &q.bar,
                            c.now,
                            &mut remaining_capacity,
                            FillContext {
                                rules: &rules,
                                price: price?,
                                opening: None,
                            },
                        )?;
                        for f in &mut self.fills[before..] {
                            f.historical_execution = Some(format!("EX_POST_OPEN_ASSUMPTION; batch={}; source={}; OPENING_OBSERVED=NOT_VERIFIED; HISTORICAL_PIT=NOT_VERIFIED; REAL_TRADABILITY=NOT_VERIFIED",batch.decision.source_sha256,c.source_sha256));
                        }
                        reason = self.orders[oi].reason.clone();
                    } else {
                        reason = format!(
                            "NO_FILL / RULE_STATUS_ACTION_OR_LIMIT_UNVERIFIED:{}",
                            q.reason
                        );
                    }
                }
            }
            if self.orders[oi].active() {
                self.expire(oi);
                self.orders[oi].reason = format!("{reason}; IOC remainder released");
            }
        }
        if timely {
            self.advance(c.now, day)?;
            self.snapshot.marks = c
                .quotes
                .iter()
                .filter(|q| {
                    q.corporate_actions_verified && q.bar.status_verified && q.bar.close > Cny::ZERO
                })
                .map(|q| PositionMark {
                    instrument: q.bar.instrument.clone(),
                    price: q.bar.close,
                    as_of: closes,
                    available_at: q.bar.available_at,
                    source: format!("EX_POST_EOD | {}", c.source_sha256),
                })
                .collect();
            self.observe()?;
        }
        let book = self.portfolio.as_mut().expect("book");
        book.pending = None;
        book.last_event_at = c.now;
        book.batches[index].finalized_at = Some(c.now);
        book.batches[index].confirmation = Some(c.clone());
        book.batches[index].reason = if timely {
            "EX_POST_OPEN_ASSUMPTION_OR_NO_FILL"
        } else {
            "NO_FILL_EXPIRED"
        }
        .into();
        Ok(())
    }
}
