// Cloudflare Workers の Cron Trigger から1時間ごとに GitHub Actions の更新を起動する。
// GitHub の予定実行（schedule）はよく抜けるので、外から workflow_dispatch で起こす。
// Worker の Secret に GITHUB_TOKEN（このリポジトリの Actions: Read and write だけを持つトークン）を入れる。
export default {
  async scheduled(event, env, ctx) {
    const r = await fetch("https://api.github.com/repos/kodaka-yutaro/brawl-showdown/actions/workflows/update.yml/dispatches", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "brawl-update-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main" }),
    });
    if (!r.ok) throw new Error(`GitHub ${r.status}: ${await r.text()}`);
  },
};
