import { Icon } from '../icons';
import { APP } from '../lib/copy';

/**
 * 侧栏底部唯一用户入口：本地单用户产品，没有账号体系，因此不提供菜单、
 * 不重复“设置”，只说明本机访问范围与版本。
 */
export function SidebarUser() {
  return (
    <div className="sidebar-account">
      <div className="account-static">
        <span className="avatar" aria-hidden="true">
          <Icon name="user" size={15} />
        </span>
        <span className="account-copy">
          <span className="account-name">本机用户</span>
          <span className="account-sub">{APP.localOnly} · v{__UI_VERSION__}</span>
        </span>
      </div>
    </div>
  );
}
