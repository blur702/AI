import { Page } from '@playwright/test';
import { BasePage } from '../base/BasePage';
import { ServiceCard } from './components/ServiceCard';
import { VRAMMonitor } from './components/VRAMMonitor';

export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  getServiceCardByName(name: string): ServiceCard {
    // Frontend uses .card class with .card-title for service name
    return new ServiceCard(this.page, `.card:has(.card-title:has-text("${name}"))`);
  }

  getVRAMMonitor(): VRAMMonitor {
    // Frontend uses .resource-manager for the VRAM/GPU section
    return new VRAMMonitor(this.page, '.resource-manager');
  }

  async getAllServiceCards(): Promise<number> {
    return this.page.locator('.card').count();
  }

  getFirstServiceCard(): ServiceCard {
    return new ServiceCard(this.page, '.card:nth-of-type(1)');
  }
}
