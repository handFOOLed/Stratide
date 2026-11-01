use super::*;
use crate::cash_dividend::{local_day, DividendPhase};

impl State {
    pub(super) fn risk_kernel(&self) -> Result<RiskKernel> {
        let k = RiskKernel::restore(self.config.clone(), self.risk.clone())?;
        if self.cash_dividends.is_some() {
            let t = self.dividend_totals()?;
            Ok(k.with_dividend_assets(money(t.receivable_fen)?, money(t.liability_fen)?)?)
        } else {
            Ok(k)
        }
    }

    pub(super) fn apply_dividend(
        &mut self,
        id: &str,
        phase: &DividendPhase,
        now: Timestamp,
        day: TradingDay,
        marks: &[PositionMark],
    ) -> Result<()> {
        let book = self
            .cash_dividends
            .as_ref()
            .ok_or("旧 v3 账本禁止注入分红/自动升级")?;
        let index = book
            .events
            .iter()
            .position(|a| a.event.event_id == id)
            .ok_or("事件未在 genesis 冻结")?;
        let a = &book.events[index];
        if a.next() != Some((phase.clone(), now, day))
            || local_day(now)? != day
            || book
                .events
                .iter()
                .filter_map(|a| a.next())
                .any(|(_, at, _)| at < now)
        {
            return Err("股息阶段重复/乱序/迟到；禁止回填".into());
        }
        // Verify record cutoff holdings are already authoritative: fills after
        // cutoff cannot enter the frozen entitlement, even within the same day.
        if *phase == DividendPhase::Record
            && self.fills.iter().any(|f| {
                f.instrument == a.event.instrument
                    && (f.evidence.closes_at > a.event.record_close_at
                        || f.evidence.available_at > now)
            })
        {
            return Err("登记日收盘后成交不能回填权益".into());
        }
        // All held assets need a fresh, nonconflicting mark at this boundary.
        // Do not change risk peak on a stale pre-ex price followed by a dividend.
        for lot in &self.snapshot.positions {
            let matches: Vec<_> = marks
                .iter()
                .filter(|m| m.instrument == lot.instrument)
                .collect();
            if matches.len() != 1
                || matches[0].as_of > now
                || matches[0].available_at > now
                || matches[0].as_of > matches[0].available_at
                || matches[0].as_of.0 < 0
                || now.0 - matches[0].as_of.0 > self.config.max_mark_age_ms
                || matches[0].price == Cny::ZERO
                || matches[0].source.trim().is_empty()
                || (*phase == DividendPhase::Ex && matches[0].as_of < a.event.ex_at)
            {
                return Err("公司行为边界缺少当时可信未复权估值，禁止确认未知NAV".into());
            }
        }
        let instrument = a.event.instrument.clone();
        let entitled = self
            .snapshot
            .positions
            .iter()
            .filter(|p| p.instrument == instrument)
            .try_fold(0, |n, p| add(n, p.quantity))?;
        self.advance(now, day)?; // day-start uses previous valid net asset value
        match phase {
            DividendPhase::Record => {
                self.cash_dividends.as_mut().unwrap().events[index].entitled_shares =
                    Some(entitled);
            }
            DividendPhase::Ex => {
                for i in 0..self.orders.len() {
                    if self.orders[i].active() && self.orders[i].proposal.instrument == instrument {
                        self.expire(i);
                        self.orders[i].reason = format!("CASH_DIVIDEND_V1/{id}：除息前旧挂单到期释放；不支持自动调价，须重新提交");
                    }
                }
                self.cash_dividends.as_mut().unwrap().events[index].recognized = true;
            }
            DividendPhase::Payment => {
                let a = &mut self.cash_dividends.as_mut().unwrap().events[index];
                let (gross, tax) = a.event.amounts(a.entitled_shares.ok_or("缺登记权益")?)?;
                self.snapshot.cash = self
                    .snapshot
                    .cash
                    .checked_add(money(gross - tax)?)
                    .map_err(|e| e.to_string())?;
                a.paid = true;
            }
        }
        self.snapshot.marks = marks.to_vec();
        self.observe()?;
        if self.valuation_error.is_some() {
            return Err("公司行为估值未知，拒绝入账".into());
        }
        Ok(())
    }
}
