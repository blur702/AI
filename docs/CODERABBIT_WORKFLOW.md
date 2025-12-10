# CodeRabbit PR Workflow for PR #6

This document explains how the CodeRabbit review workflow operates for
PR **#6** (`fix/startup-scripts-and-n8n-setup`) and how to iterate on fixes
until the pull request is approved.

## Current PR Status

- **Branch**: `fix/startup-scripts-and-n8n-setup`  
- **PR URL**: <https://github.com/blur702/AI/pull/6>  
- **Review Status**: Changes Requested (134+ comments)  
- **Tracking Doc**: `docs/CODERABBIT_ISSUES.md`

## High-Level Workflow

```text
1. Push commits to branch
   git add . && git commit -m "fix: ..." && git push
                           ↓
2. CodeRabbit automatically reviews within ~2-5 minutes
                           ↓
3. View results at: https://github.com/blur702/AI/pull/6
   - Click "Files changed" tab to see inline comments
   - CodeRabbit bot comments appear in Conversation tab
                           ↓
4. Fix issues locally, commit, push
                           ↓
5. CodeRabbit re-reviews automatically
                           ↓
6. When approved → Merge PR into master
```

## Quick Commands

```bash
# See current status
gh pr view 6

# Push a fix (triggers re-review)
git add <file> && git commit -m "fix: description" && git push

# View PR in browser
gh pr view 6 --web
```

## Where to See Results

1. **GitHub PR page**: <https://github.com/blur702/AI/pull/6>  
2. **Files changed** tab: Shows inline comments on specific lines  
3. **Conversation** tab: Shows CodeRabbit summary comments  

## Pull Request & CodeRabbit Workflow

### What is PR #6?

A Pull Request (PR) is a request to merge changes from the branch
`fix/startup-scripts-and-n8n-setup` into `master`. CodeRabbit is an AI bot
that automatically reviews the code when new commits are pushed.

### Life of a Change

1. You make edits locally.
2. You stage and commit changes:

   ```bash
   git add <file>
   git commit -m "fix: description of fix"
   ```

3. You push the commit to the PR branch:

   ```bash
   git push
   ```

4. CodeRabbit runs automatically (typically within 2–5 minutes).
5. Review results appear on the PR:
   - Inline comments under **Files changed**
   - Summary and discussion from `coderabbitai` bot under **Conversation**
6. You repeat the cycle (edit → commit → push) until CodeRabbit shows
   an **Approved** review.

### How to Get PR #6 Approved

1. Work through all issues documented in `docs/CODERABBIT_ISSUES.md`.  
2. For each batch of fixes:
   - Commit with a clear message (e.g., `fix: address CodeRabbit feedback for X`).
   - Push to the `fix/startup-scripts-and-n8n-setup` branch.
3. Wait for CodeRabbit to complete its review.
4. When CodeRabbit marks the PR as **Approved**, proceed to merge the PR
   into `master`.

