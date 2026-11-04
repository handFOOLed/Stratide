use super::*;

impl State {
    /// This branch models an unobserved historical open. It deliberately never
    /// constructs OpeningEvidence and never inspects high/low/close/volume to
    /// qualify a fill. The close is observed only AFTER execution accounting.
    pub(crate) fn historical_next_open(
        &mut self,
        b: &DailyBar,
        rules: &TradingRules,
        now: Timestamp,
    ) -> Result<()> {
        // A v4 ex/payment reducer may have just valued this exact opening.
        // Permit that clock boundary only; v3's strict-before-open rule remains.
        let dividend_open = self.cash_dividends.as_ref().is_some_and(|book| {
            book.events.iter().any(|a| {
                a.event.instrument == b.instrument
                    && ((a.recognized && a.event.ex_at == b.opens_at)
                        || (a.paid && a.event.payment_at == b.opens_at))
            })
        });
        if self.provenance.mode != DataMode::HistoricalReplay
            || b.provenance != self.provenance
            || b.instrument != rules.instrument
            || b.day != rules.trading_day
            || !b.day.is_valid()
            || self.snapshot.as_of > b.opens_at
            || (self.snapshot.as_of == b.opens_at && !dividend_open)
            || self.snapshot.trading_day > b.day
            || b.opens_at >= b.closes_at
            || b.closes_at > b.available_at
            || b.available_at > now
            || now.0 - b.closes_at.0 > self.config.max_mark_age_ms
            || rules.available_at > now
            || rules.available_at.0 < 0
            || rules.source.trim().is_empty()
            || rules.settlement != SettlementRule::TPlusOne
            || rules.buy_lot != 100
            || rules.sell_lot != 100
            || rules.tick_size.fen() != 1
            || rules.min_price == Cny::ZERO
            || rules.max_price <= rules.min_price
            || b.open == Cny::ZERO
            || b.close == Cny::ZERO
            || self.sessions.contains(&(b.instrument.clone(), b.day))
            || self
                .snapshot
                .positions
                .iter()
                .any(|p| p.instrument != b.instrument)
            || self
                .snapshot
                .pending_orders
                .iter()
                .any(|p| p.instrument != b.instrument)
        {
            return Err("历史 next-open v1 模式/单证券/时间/规则无效；不得代替独立开盘证据".into());
        }

        // These are modeled timestamps, explicitly tagged as an ex-post
        // assumption. Neither these marks nor rules enter a forward journal.
        let mut modeled_rules = rules.clone();
        modeled_rules.available_at = b.opens_at;
        modeled_rules.source =
            format!("historical_ex_post_execution_assumption | {}", rules.source);
        self.advance(b.opens_at, b.day)?;
        self.snapshot.marks = vec![PositionMark {
            instrument: b.instrument.clone(),
            price: b.open,
            as_of: b.opens_at,
            available_at: b.opens_at,
            source: "historical_ex_post_execution_assumption/next-open-adverse-tick-100-v1".into(),
        }];
        self.observe()?;
        let mut capacity = 100; // Precommitted, not inferred from next-day volume.
        for index in 0..self.orders.len() {
            let order = &self.orders[index];
            if !order.active() || order.proposal.instrument != b.instrument {
                continue;
            }
            if b.opens_at >= order.proposal.expires_at {
                self.expire(index);
                continue;
            }
            let p = &order.proposal;
            let price = if p.side == Side::Buy {
                b.open.fen().checked_add(1)
            } else {
                b.open.fen().checked_sub(1)
            }
            .and_then(|v| money(v).ok());
            let eligible = b.status_verified
                && modeled_rules.tradable
                && order.accepted_on < b.day
                && p.decision_at < b.opens_at
                && p.data_available_at < b.opens_at
                && p.earliest_execution_at <= b.opens_at
                && price.is_some_and(|price| {
                    price > rules.min_price
                        && price < rules.max_price
                        && b.open > rules.min_price
                        && b.open < rules.max_price
                        && if p.side == Side::Buy {
                            price <= p.limit_price
                        } else {
                            price >= p.limit_price
                        }
                });
            if eligible {
                // The enclosing ledger transaction rolls back accounting errors;
                // all accepted fills still pass the shared mandatory risk path.
                self.fill_order(
                    index,
                    b,
                    now,
                    &mut capacity,
                    FillContext {
                        rules: &modeled_rules,
                        price: price.unwrap(),
                        opening: None,
                    },
                )?;
            } else {
                self.orders[index].reason =
                    "历史模型缺状态/规则、非后续开盘、封板或不利跳空超过原限价；不成交".into();
            }
        }
        self.advance(now, b.day)?;
        self.snapshot.marks = if b.status_verified {
            vec![PositionMark {
                instrument: b.instrument.clone(),
                price: b.close,
                as_of: b.closes_at,
                available_at: b.available_at,
                source: format!(
                    "assumed_historical_eod_availability_not_pit_verified | {}",
                    b.provenance.source_version
                ),
            }]
        } else {
            vec![]
        };
        // One next session only (IOC in this model), including risk rejection or
        // insufficient capacity. Preserve the reason rather than leaving stale
        // signals active for a later favorable session.
        for index in 0..self.orders.len() {
            if self.orders[index].active() {
                let reason = self.orders[index].reason.clone();
                self.expire(index);
                self.orders[index].reason = format!("{reason}；历史 next-session IOC 余量释放");
            }
        }
        self.sessions.push((b.instrument.clone(), b.day));
        self.observe()
    }
}
