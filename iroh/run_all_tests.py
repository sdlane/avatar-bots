"""
Main test runner for the Iroh wargame configuration system.
Runs all tests sequentially with proper setup and cleanup.
"""
import asyncio
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_all_tests():
    """Run all configuration tests in sequence"""
    logger.info("\n" + "="*60)
    logger.info("IROH WARGAME CONFIGURATION SYSTEM - FULL TEST SUITE")
    logger.info("="*60)
    logger.info("This test suite will:")
    logger.info("  1. Set up test server")
    logger.info("  2. Set up test characters")
    logger.info("  3. Run configuration import/export tests")
    logger.info("  4. Clean up test characters")
    logger.info("  5. Clean up test server")
    logger.info("  6. Verify all data was cleaned up")
    logger.info("="*60)

    all_passed = True

    # Step 1: Set up test server
    try:
        logger.info("\n[1/5] Setting up test server...")
        from test_setup_server import setup_test_server, cleanup_test_server

        success = await setup_test_server()
        if not success:
            logger.error("❌ Failed to set up test server")
            return False
    except Exception as e:
        logger.error(f"❌ Error setting up test server: {e}")
        return False

    try:
        # Step 2: Set up test characters
        try:
            logger.info("\n[2/5] Setting up test characters...")
            from test_setup_characters import setup_test_characters, cleanup_test_characters

            success = await setup_test_characters()
            if not success:
                logger.error("❌ Failed to set up test characters")
                all_passed = False
        except Exception as e:
            logger.error(f"❌ Error setting up test characters: {e}")
            all_passed = False

        # Step 3: Run configuration tests
        if all_passed:
            try:
                logger.info("\n[3/5] Running configuration tests...")
                from test_config import run_all_tests as run_config_tests

                success = await run_config_tests()
                if not success:
                    logger.error("❌ Configuration tests failed")
                    all_passed = False
            except Exception as e:
                logger.error(f"❌ Error running configuration tests: {e}")
                import traceback
                traceback.print_exc()
                all_passed = False

        # Step 4: Clean up test characters
        try:
            logger.info("\n[4/5] Cleaning up test characters...")
            success = await cleanup_test_characters()
        except Exception as e:
            logger.error(f"❌ Error cleaning up test characters: {e}")

        # Step 5: Clean up test server
        try:
            logger.info("\n[5/5] Cleaning up test server...")
            success = await cleanup_test_server()
        except Exception as e:
            logger.error(f"❌ Error cleaning up test server: {e}")

        # Step 6: Verify cleanup
        try:
            logger.info("\n[6/6] Verifying cleanup...")
            from verify_cleanup import verify_cleanup

            cleanup_success = await verify_cleanup()
            if not cleanup_success:
                logger.warning("⚠️ Cleanup verification found remaining data")
        except Exception as e:
            logger.error(f"❌ Error verifying cleanup: {e}")

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Tests interrupted by user")
        # Still try to clean up
        try:
            from test_setup_characters import cleanup_test_characters
            await cleanup_test_characters()
        except:
            pass
        try:
            from test_setup_server import cleanup_test_server
            await cleanup_test_server()
        except:
            pass
        return False

    # Final summary
    logger.info("\n" + "="*60)
    logger.info("FINAL TEST RESULTS")
    logger.info("="*60)

    if all_passed:
        logger.info("🎉 All tests passed!")
        logger.info("✅ Test server setup/cleanup: PASSED")
        logger.info("✅ Test characters setup/cleanup: PASSED")
        logger.info("✅ Configuration import/export: PASSED")
    else:
        logger.info("⚠️ Some tests failed - check logs above")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
