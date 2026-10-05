"""Fixed native80 panel semantics. Pure protocol/model; no driver loading here."""
import time
from nlya_pmc2_query import Pmc2Query, CHIP, BUILD, POLICY
from nlya_policy_trial import TrialProtocol, validate_telemetry, restored
from inpout_status_probe import utc

ADAPTER_FIELDS = (0x0340, 0x03a4)


class PanelReader(Pmc2Query):
    def __init__(self, owner):
        self.owner = owner
        super().__init__(owner.read, owner.write, owner.now, owner.sleep)

    def read_known(self, address):
        if address not in CHIP + BUILD + POLICY + ADAPTER_FIELDS:
            raise RuntimeError('Address outside panel fixed read allowlist')
        if self.queries >= 25 or self.owner.queries >= 256:
            raise RuntimeError('Panel query budget exhausted')
        deadline = self.now() + 1
        self.owner.transport_safe = False
        self.wait(False, deadline)
        self.queries += 1
        self.owner.queries += 1
        self.write(0x6c, 0x92)
        self.wait(False, deadline)
        self.write(0x68, address >> 8)
        self.wait(False, deadline)
        self.write(0x68, address & 255)
        self.wait(True, deadline)
        value = self.read(0x68)
        self.wait(False, deadline)
        self.owner.transport_safe = True
        return value


class PanelProtocol(TrialProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transport_safe = True
    def reader(self):
        return PanelReader(self)
    def enable_80(self):
        if self.set_attempted:
            raise RuntimeError('Setter cannot be retried')
        q, deadline = self.reader(), self.now() + 1
        q.wait(False, deadline)
        self.transport_safe = False
        self.set_attempted = True
        self.write(0x6c, 0x73)
        q.wait(False, deadline)
        self.write(0x68, 0x50)
        q.wait(False, deadline)
        self.transport_safe = True
    def cancel(self):
        if self.cancel_attempted:
            raise RuntimeError('Cancel cannot be retried')
        q, deadline = self.reader(), self.now() + 1
        q.wait(False, deadline)
        self.transport_safe = False
        self.cancel_attempted = True
        self.write(0x6c, 0x74)
        q.wait(False, deadline)
        self.transport_safe = True


def snapshot(protocol, get_telemetry):
    identity = protocol.identity()
    if not identity['policy_target_stable']:
        raise RuntimeError('Unstable policy readback')
    fields = []
    for _ in range(2):
        q = protocol.reader()
        fields.append({f'{a:04X}': q.read_known(a) for a in ADAPTER_FIELDS})
    if any((fields[0][k] ^ fields[1][k]) & mask for k, mask in [('0340', 8), ('03A4', 1)]):
        raise RuntimeError('Unstable adapter/battery presence readback')
    p = identity['groups'][-1]
    error, t = None, None
    try:
        t = get_telemetry()
        validate_telemetry(t, ac_required=False)
        if abs(p['0396'] - t['soc']) > 2:
            raise RuntimeError('EC/Windows SOC disagreement')
    except Exception as exc:
        error = str(exc)
        t = None
    return {'utc': utc(), 'identity': identity, 'policy': p,
            'adapter_fields': fields, 'ec_adapter_present': bool(fields[-1]['0340'] & 8),
            'ec_battery_present': bool(fields[-1]['03A4'] & 1),
            'enabled': bool(p['0475'] & 128), 'target': p['0475'] & 127,
            'learn_requested': bool(p['03A6'] & 2),
            'branch': p['0476'] & 0xf0, 'telemetry': t, 'telemetry_error': error}


def confirm(protocol, enabled, sleep):
    count, reads = 0, []
    for _ in range(6):
        p = protocol.policy()
        reads.append(p)
        valid = p['0475'] == 0xd0 if enabled else restored(p)
        count = count + 1 if valid else 0
        if count == 3:
            return reads
        sleep(.3)
    raise RuntimeError('Native policy readback mismatch; no command retry')


def operate(protocol, action, get_telemetry, state, save, *, allow_high_soc=False,
            sleep=time.sleep):
    if action not in ('status', 'enable', 'disable'):
        raise RuntimeError('Only status/enable80/cancel are available')
    if state.get('transport_fault') or state.get('recovery_required'):
        raise RuntimeError('Unresolved transport/operation; all further queries and control blocked')
    try:
        s = snapshot(protocol, get_telemetry)
    except Exception:
        if not protocol.transport_safe:
            state.update(transport_fault=True, transport_safe=False)
            save()
        raise
    state.update(last_snapshot=s, keep_after_close=True, transport_safe=protocol.transport_safe)
    save()
    if action == 'status':
        return s
    groups = s['identity']['groups']
    if any(p['0475'] not in (0x3c, 0xd0) for p in groups):
        raise RuntimeError('Unrecognized existing policy; not overwritten')
    if action == 'enable' and s['enabled']:
        return s
    if action == 'disable' and all(restored(p) for p in groups):
        return s
    if action == 'enable':
        if not all(restored(p) and not p['03A6'] & 0x80 for p in groups):
            raise RuntimeError('Baseline is not verified default policy')
        if not s['telemetry']:
            raise RuntimeError('Valid telemetry required before enable')
        validate_telemetry(s['telemetry'])
        if not s['ec_adapter_present'] or not s['ec_battery_present']:
            raise RuntimeError('EC adapter/battery presence required')
        if max(s['policy']['0396'], s['telemetry']['soc']) > 80 and not allow_high_soc:
            raise RuntimeError('Above80 native active discharge requires explicit acknowledgement')
    state.update(baseline_policy=s['policy'], recovery_required=True,
                 policy_set_attempted=action == 'enable', cancel_attempted=action == 'disable',
                 transport_safe=False, action=action, action_started_utc=utc())
    save()  # Durable intent before the first control byte.
    try:
        if action == 'enable': protocol.enable_80()
        else: protocol.cancel()
        state['transport_safe'] = protocol.transport_safe
        save()
        state['confirmation'] = confirm(protocol, action == 'enable', sleep)
        state.update(recovery_required=False, operation_verified=True,
                     owned_active=action == 'enable', action_finished_utc=utc())
        save()
        s = snapshot(protocol, get_telemetry)
        # If telemetry fails immediately after enable, cancel once rather than
        # claim healthy monitoring. Windows AC changes alone are not failure.
        if action == 'enable' and s['telemetry_error']:
            state['recovery_required'] = True
            save()
            raise RuntimeError(s['telemetry_error'])
        state.update(last_snapshot=s, transport_safe=protocol.transport_safe)
        save()
        return s
    except Exception as exc:
        state.update(operation_error=str(exc), transport_safe=protocol.transport_safe)
        if not protocol.transport_safe: state['transport_fault'] = True
        save()
        if action == 'enable' and state['recovery_required'] and protocol.transport_safe:
            state['cancel_attempted'] = True
            save()
            try:
                protocol.cancel()
                state['recovery_confirmation'] = confirm(protocol, False, sleep)
                state.update(recovery_required=False, recovery_verified=True, owned_active=False)
            except Exception as recovery:
                state['recovery_error'] = str(recovery)
            state['transport_safe'] = protocol.transport_safe
            if not protocol.transport_safe: state['transport_fault'] = True
            save()
        raise
