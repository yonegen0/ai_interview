/** @file dialog.test.tsx @description 終了確認のキーボードとフォーカス復帰 */
import { useState } from "react";
import { expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog } from "@/components/organisms/Dialog";
const Example = () => { const [open, setOpen] = useState(false); return <><button onClick={() => setOpen(true)}>終了確認</button><Dialog open={open} onClose={() => setOpen(false)} title="練習を終了しますか？" content={<p>下書きを破棄します。</p>} actions={<button autoFocus onClick={() => setOpen(false)}>続ける</button>} /></>; };
it("returns focus to the trigger when cancelled with Escape", async () => {
  const user = userEvent.setup(); render(<Example />);
  const trigger = screen.getByRole("button", { name: "終了確認" });
  await user.click(trigger); await waitFor(() => expect(screen.getByRole("button", { name: "続ける" })).toHaveFocus());
  await user.keyboard("{Escape}"); await waitFor(() => expect(trigger).toHaveFocus());
});
