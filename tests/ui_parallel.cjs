const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
    const artifacts = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifacts, { recursive: true });
    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.EDGE_PATH || undefined
    });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = [];
    const submissions = [];

    page.on('pageerror', error => {
        errors.push(error.message);
        console.error('Page error:', error.message);
    });
    page.on('console', message => {
        if (message.type() === 'error') console.error('Browser console:', message.text());
    });
    await page.addInitScript(() => {
        localStorage.setItem('mooc_configured', 'true');
    });

    await page.route('**/api/users', route => route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([
            {
                username: 'demo_account',
                user_key: 'site-a-user',
                site: 'site-a.example.test',
                base_url: 'https://site-a.example.test',
                school_id: 0,
                password: ''
            },
            {
                username: 'demo_account',
                user_key: 'site-b-user',
                site: 'site-b.example.test',
                base_url: 'https://site-b.example.test',
                school_id: 0,
                password: ''
            }
        ])
    }));
    await page.route('**/api/status', route => route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ running_users: 0, total_users: 0, users: [] })
    }));
    await page.route('**/api/parallel/courses', route => route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
            success: true,
            courses: [
                { id: '101', name: '大学英语（一）', progress: 0.25, progress_text: '25%' },
                { id: '102', name: '计算机程序设计基础', progress: 0.5, progress_text: '50%' },
                { id: '103', name: '一门用于检查长课程名称在窄屏中自动换行的测试课程', progress: 0, progress_text: '0%' }
            ]
        })
    }));
    await page.route('**/api/parallel/start', async route => {
        submissions.push(route.request().postDataJSON());
        await route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({ success: true, message: '模拟并行任务已启动' })
        });
    });
    await page.route('**/socket.io/4.0.1/socket.io.js', route => route.fulfill({
        contentType: 'application/javascript',
        body: 'window.io = function () { return { on: function () {} }; };'
    }));

    await page.goto('http://127.0.0.1:10086', { waitUntil: 'domcontentloaded' });
    await page.locator('.menu-item[data-tab="users"]').click();
    await page.locator('.user-item').first().waitFor();
    assert.equal(await page.locator('.user-item').count(), 2);
    assert.equal(await page.locator('.user-site').nth(1).textContent(), 'site-b.example.test');
    await page.locator('.btn-parallel-user').nth(1).click();
    await page.locator('.parallel-course-row').first().waitFor();
    assert.equal(await page.locator('.parallel-course-row').count(), 3);

    const second = page.locator('.parallel-course-row').nth(1);
    await second.locator('.parallel-course-checkbox').uncheck();
    assert.equal(await second.locator('.parallel-course-mode').isDisabled(), true);
    await second.locator('.parallel-course-checkbox').check();
    await page.locator('.parallel-course-row').nth(0).locator('select').selectOption('parallel');
    await second.locator('select').selectOption('auto');
    await page.locator('.parallel-course-row').nth(2).locator('select').selectOption('sequential');
    await page.locator('#parallelNodeLimit').fill('4');
    await page.locator('#parallelCourseLimit').fill('2');
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(artifacts, 'parallel-desktop.png'), fullPage: true });

    await page.locator('#parallelStartBtn').click();
    await page.locator('#parallelModal').waitFor({ state: 'hidden' });
    assert.equal(submissions.length, 1);
    assert.equal(submissions[0].user_key, 'site-b-user');
    assert.deepEqual(submissions[0].course_ids, ['101', '102', '103']);
    assert.deepEqual(submissions[0].course_modes, {
        '101': 'parallel',
        '102': 'auto',
        '103': 'sequential'
    });
    assert.equal(submissions[0].node_limit, 4);
    assert.equal(submissions[0].course_limit, 2);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.btn-parallel-user').first().click();
    await page.locator('.parallel-course-row').first().waitFor();
    await page.waitForTimeout(250);
    const widths = await page.evaluate(() => {
        const dialog = document.querySelector('.parallel-dialog').getBoundingClientRect();
        const longest = document.querySelectorAll('.parallel-course-row')[2].getBoundingClientRect();
        return {
            viewport: document.documentElement.clientWidth,
            page: document.documentElement.scrollWidth,
            dialogRight: dialog.right,
            courseRight: longest.right
        };
    });
    await page.screenshot({ path: path.join(artifacts, 'parallel-mobile.png'), fullPage: true });
    assert.ok(widths.dialogRight <= widths.viewport, JSON.stringify(widths));
    assert.ok(widths.courseRight <= widths.dialogRight + 1, JSON.stringify(widths));

    assert.deepEqual(errors, []);
    console.log('UI checks passed: course modes, payload, desktop and mobile layout.');
    await browser.close();
})().catch(error => {
    console.error(error);
    process.exit(1);
});
